from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

from datetime import datetime, timezone, timedelta
from src.hashing import sha256_file
from src.config import load_config
from src.logger import setup_logger
from src.database import ArchiveDatabase
from src.scanner import QueueScanner
from src.telegram_client import TelegramClient
from src.uploader import ArchiveUploader
from src.cleanup import ArchiveCleanup

async def main() -> int:
    parser = argparse.ArgumentParser(description="Telegram Media Archive")
    parser.add_argument("--dry-run", action="store_true", help="Run without modifying database or moving files")
    parser.add_argument("--hash-file", type=Path, help="Only hash a specific file and exit")
    args = parser.parse_args()

    if args.hash_file:
        digest = sha256_file(args.hash_file)
        print(f"{args.hash_file.name}: {digest}")
        return 0

    try:
        config = load_config()
    except Exception as e:
        print(f"Failed to load configuration: {e}", file=sys.stderr)
        return 1

    if args.dry_run:
        config.app.dry_run = True

    logger = setup_logger(config)
    
    if config.app.dry_run:
        logger.info("Starting in DRY RUN mode. No database modifications will occur.")
    else:
        logger.info("Starting in LIVE mode.")
        
    logger.info(f"Python Executable: {sys.executable}")
    logger.info(f"Python Version: {sys.version.split()[0]}")
    
    try:
        from src.face_engine import OPENCV_AVAILABLE, cv2, Cv2FaceEngine
        if OPENCV_AVAILABLE:
            logger.info(f"OpenCV Version: {cv2.__version__}")
        else:
            logger.info("OpenCV: unavailable")
    except ImportError:
        OPENCV_AVAILABLE = False
        logger.info("OpenCV: unavailable")

    face_engine_loaded = False
    if not config.faces.enabled:
        logger.info("Face analysis disabled; models were not loaded.")
    else:
        if not OPENCV_AVAILABLE:
            logger.error("Configuration error: Face processing dependency unavailable: install the Phase 5 requirements.")
        else:
            try:
                engine = Cv2FaceEngine(config=config.faces, logger=logger)
                engine.load_models()
                face_engine_loaded = True
                logger.info(f"Detector: {Cv2FaceEngine.DETECTOR_MANIFEST.filename} (v{Cv2FaceEngine.DETECTOR_MANIFEST.version}) SHA256: {engine.detector_hash}")
                logger.info(f"Recognizer: {Cv2FaceEngine.RECOGNIZER_MANIFEST.filename} (v{Cv2FaceEngine.RECOGNIZER_MANIFEST.version}) SHA256: {engine.recognizer_hash}")
                logger.info(f"Model Identity: {engine.model_identity()}")
            except Exception as e:
                logger.error(f"Configuration error: Face processing dependency unavailable or models missing: {e}")

    application_run_started_at = datetime.now(timezone.utc)
    eligible_before = (application_run_started_at - timedelta(days=config.cleanup.backup_safety_days)).isoformat()

    db = ArchiveDatabase(config.app.database_path)
    
    # Run migrations
    sql_dir = Path("sql")
    if sql_dir.exists():
        db.apply_migrations(Path("sql"))
    if not config.app.dry_run:
        db.repair_legacy_routing(config)
        db.recover_failed_original_uploads()

    cleanup_worker = ArchiveCleanup(config, db, logger)
    cleanup_worker.reconcile_in_progress()

    scanner = QueueScanner(config, db, logger)
    candidates = scanner.scan_once()
    
    if face_engine_loaded:
        from src.face_analysis import FaceAnalysisWorker
        face_worker = FaceAnalysisWorker(config=config, database=db, engine=engine, logger=logger)
        if config.app.dry_run:
            face_worker.analyze_candidates(candidates)
        else:
            face_worker.analyze_pending()

    if config.secrets.bot_token:
        telegram = TelegramClient(config.secrets.bot_token, "https://api.telegram.org")
        uploader = ArchiveUploader(config, db, telegram, logger)
        await uploader.upload_once()
    else:
        logger.warning("No Telegram bot token found. Skipping upload phase.")

    cleanup_worker.run_cleanup(eligible_before)

    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
