import argparse
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import load_config
from src.database import ArchiveDatabase
from src.logger import setup_logger
from src.face_policy import CURRENT_ANALYSIS_VERSION

def main():
    parser = argparse.ArgumentParser(description="Safely requeue images for face analysis")
    parser.add_argument("--commit", action="store_true", help="Apply changes to the database")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of eligible records to requeue (0 = unlimited)")
    parser.add_argument("--media-id", type=int, help="Test only one specific record ID")
    
    args = parser.parse_args()
    
    config = load_config()
    logger = setup_logger(config)
    db = ArchiveDatabase(config.app.database_path)
    
    try:
        conn = db.connect()
        # Query candidates
        query = """
            SELECT m.id, m.original_path, m.original_filename, m.cleanup_state, m.state,
                   COALESCE(MAX(fa.analysis_version), 0) as latest_version
            FROM media m
            LEFT JOIN face_analysis_attempts fa ON m.id = fa.media_id AND fa.outcome = 'SUCCESS'
            WHERE m.media_type = 'image'
        """
        
        params = []
        if args.media_id:
            query += " AND m.id = ?"
            params.append(args.media_id)
            
        query += " GROUP BY m.id"
        
        records = conn.execute(query, params).fetchall()
        conn.close()
    except Exception as e:
        logger.error("Failed to query database: %s", e)
        sys.exit(1)
        
    scanned = len(records)
    already_current = 0
    missing_file = 0
    cleaned = 0
    eligible = []
    
    for r in records:
        latest_version = r["latest_version"]
        
        if latest_version >= CURRENT_ANALYSIS_VERSION:
            already_current += 1
            continue
            
        if r["cleanup_state"] == "COMPLETED" or r["state"] == "CLEANED":
            cleaned += 1
            continue
            
        original_path = Path(r["original_path"])
        if not original_path.is_file():
            missing_file += 1
            continue
            
        eligible.append(r["id"])
        
    # Apply limit
    limited_skipped = 0
    if args.limit > 0 and len(eligible) > args.limit:
        limited_skipped = len(eligible) - args.limit
        eligible = eligible[:args.limit]
        
    requeued = len(eligible)
    errors = 0
    
    if args.commit and eligible:
        try:
            with db.transaction() as conn:
                for mid in eligible:
                    conn.execute("UPDATE media SET face_state = 'PENDING' WHERE id = ?", (mid,))
        except Exception as e:
            logger.error("Transaction failed, rolled back: %s", e)
            errors = len(eligible)
            requeued = 0
    
    print(f"--- Requeue Summary ---")
    print(f"Mode            : {'COMMIT' if args.commit else 'DRY-RUN'}")
    print(f"Target Version  : {CURRENT_ANALYSIS_VERSION}")
    print(f"Scanned         : {scanned}")
    print(f"Already Current : {already_current}")
    print(f"Missing File    : {missing_file}")
    print(f"Cleaned         : {cleaned}")
    print(f"Eligible        : {len(eligible) + limited_skipped}")
    print(f"Limited/Skipped : {limited_skipped}")
    print(f"Requeued        : {requeued}")
    print(f"Errors          : {errors}")

if __name__ == "__main__":
    main()
