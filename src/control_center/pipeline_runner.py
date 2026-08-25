"""
Control Center Controlled Pipeline Runner.
Provides explicit in-memory guarantees:
- Live Pipeline: Telegram enabled, DRY RUN = False, Cleanup FORCED OFF.
- Dry Run Pipeline: DRY RUN = True, Cleanup = False.
- Cleanup Preview: DRY RUN = True, Cleanup = True (preview candidates without deleting/moving).
- Configuration Snapshot: Saved into data/control_center_snapshots/ before live runs.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import asdict, is_dataclass
import yaml

from src.config import load_config
from src.database import ArchiveDatabase
from src.logger import setup_logger
from src.logging_utils import RuntimeOptions
from src.main import run_pipeline
from src.cleanup import ArchiveCleanup


def _to_serializable_dict(obj):
    if is_dataclass(obj):
        return {k: _to_serializable_dict(v) for k, v in asdict(obj).items()}
    elif isinstance(obj, Path):
        return str(obj)
    elif isinstance(obj, (list, tuple)):
        return [_to_serializable_dict(x) for x in obj]
    elif isinstance(obj, dict):
        return {k: _to_serializable_dict(v) for k, v in obj.items()}
    return obj


def save_config_snapshot(config, mode: str) -> Path:
    snapshot_dir = Path("data/control_center_snapshots")
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_file = snapshot_dir / f"{ts}_{mode}.yaml"

    cfg_dict = _to_serializable_dict(config)
    # Redact secrets
    if "secrets" in cfg_dict and isinstance(cfg_dict["secrets"], dict):
        for k in cfg_dict["secrets"]:
            cfg_dict["secrets"][k] = "REDACTED"

    with open(snapshot_file, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg_dict, f, default_flow_style=False)

    return snapshot_file


async def run_controlled_pipeline(
    mode: str,
    verbose_private: bool = False
) -> int:
    try:
        config = load_config()
    except Exception as e:
        print(f"Failed to load configuration: {e}", file=sys.stderr)
        return 1

    opts = RuntimeOptions(verbose_private=verbose_private)

    if mode == "live":
        config.app.dry_run = False
        # GUARANTEED SAFETY INVARIANT: Cleanup is strictly forced OFF for live pipeline runs through Control Center.
        config.cleanup.enabled = False

        # Save config audit snapshot
        snapshot_path = save_config_snapshot(config, "pipeline_live")

        logger = setup_logger(config, verbose_private=opts.verbose_private)
        logger.info("=================================================================")
        logger.info("Starting Controlled Pipeline in LIVE mode")
        logger.info("Config snapshot saved: %s", snapshot_path)
        logger.info("Safety Invariant: Cleanup is FORCED OFF for this execution")
        logger.info("Telegram writes: ENABLED")
        logger.info("=================================================================")
        return await run_pipeline(config, logger, opts)

    elif mode == "dry_run":
        config.app.dry_run = True
        config.cleanup.enabled = False
        logger = setup_logger(config, verbose_private=opts.verbose_private)
        logger.info("=================================================================")
        logger.info("Starting Controlled Pipeline in DRY RUN mode")
        logger.info("Database writes: DISABLED | Telegram writes: DISABLED")
        logger.info("=================================================================")
        return await run_pipeline(config, logger, opts)

    elif mode == "cleanup_preview":
        config.app.dry_run = True
        config.cleanup.enabled = True
        logger = setup_logger(config, verbose_private=opts.verbose_private)
        logger.info("=================================================================")
        logger.info("Starting Cleanup Preview (DRY RUN)")
        logger.info("Read-only analysis of eligible cleanup candidates")
        logger.info("No files will be moved or deleted")
        logger.info("=================================================================")
        db = ArchiveDatabase(config.app.database_path)
        sql_dir = Path("sql")
        if sql_dir.exists():
            db.apply_migrations(sql_dir)
        cleanup_worker = ArchiveCleanup(config, db, logger, opts=opts)
        cleanup_worker.run_cleanup()
        logger.info("Cleanup preview complete.")
        return 0

    else:
        print(f"Unknown pipeline mode: {mode}", file=sys.stderr)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Control Center Controlled Pipeline Runner")
    parser.add_argument(
        "--mode",
        choices=["live", "dry_run", "cleanup_preview"],
        required=True,
        help="Pipeline execution mode"
    )
    parser.add_argument(
        "--verbose-private",
        action="store_true",
        help="Enable private data logging at DEBUG level"
    )
    args = parser.parse_args()
    return asyncio.run(run_controlled_pipeline(args.mode, verbose_private=args.verbose_private))


if __name__ == "__main__":
    sys.exit(main())
