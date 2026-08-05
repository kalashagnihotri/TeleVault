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
from src.logging_utils import RuntimeOptions

async def main() -> int:
    parser = argparse.ArgumentParser(description="Telegram Media Archive")
    parser.add_argument("--dry-run", action="store_true", help="Run without modifying database or moving files")
    parser.add_argument("--hash-file", type=Path, help="Only hash a specific file and exit")
    parser.add_argument("--verbose-private", action="store_true", help="Enable private data logging at DEBUG level")
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

    opts = RuntimeOptions(verbose_private=args.verbose_private)
    logger = setup_logger(config, verbose_private=opts.verbose_private)
    
    if config.app.dry_run:
        logger.info("Starting in DRY RUN mode. No database modifications will occur.")
    else:
        logger.info("Starting in LIVE mode.")
        
    logger.info("Python Executable: %s", sys.executable)
    logger.info("Python Version: %s", sys.version.split()[0])
    
    try:
        from src.face_engine import OPENCV_AVAILABLE, cv2, Cv2FaceEngine
        if OPENCV_AVAILABLE:
            logger.info("OpenCV Version: %s", cv2.__version__)
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
                logger.info("Detector: %s (v%s) SHA256: %s", Cv2FaceEngine.DETECTOR_MANIFEST.filename, Cv2FaceEngine.DETECTOR_MANIFEST.version, engine.detector_hash)
                logger.info("Recognizer: %s (v%s) SHA256: %s", Cv2FaceEngine.RECOGNIZER_MANIFEST.filename, Cv2FaceEngine.RECOGNIZER_MANIFEST.version, engine.recognizer_hash)
                logger.info("Model Identity: %s", engine.model_identity())
            except Exception as e:
                logger.error("Configuration error: Face processing dependency unavailable or models missing: %s", type(e).__name__)

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

    cleanup_worker = ArchiveCleanup(config, db, logger, opts=opts)
    cleanup_worker.reconcile_in_progress()

    scanner = QueueScanner(config, db, logger, opts=opts)
    candidates = scanner.scan_once()
    
    if face_engine_loaded:
        from src.face_analysis import FaceAnalysisWorker
        face_worker = FaceAnalysisWorker(config=config, database=db, engine=engine, logger=logger, opts=opts)
        if config.app.dry_run:
            face_worker.analyze_candidates(candidates)
        else:
            face_worker.analyze_pending()

    if config.secrets.bot_token:
        telegram = TelegramClient(config.secrets.bot_token, "https://api.telegram.org")
        uploader = ArchiveUploader(config, db, telegram, logger, opts=opts)
        await uploader.upload_once()
    else:
        logger.warning("No Telegram bot token found. Skipping upload phase.")

    cleanup_worker.run_cleanup(eligible_before)

    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
