from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4

from src.config import Config
from src.database import ArchiveDatabase
from src.hashing import sha256_file
from src.logging_utils import RuntimeOptions, ProcessingStage, log_private, safe_candidate_id


class CleanupError(Exception):
    pass


class ArchiveCleanup:
    def __init__(self, config: Config, db: ArchiveDatabase, logger: logging.Logger, opts: RuntimeOptions | None = None):
        self.config = config
        self.db = db
        self.logger = logger
        self._dry_run = config.app.dry_run
        self.opts = opts or RuntimeOptions()

    def reconcile_in_progress(self) -> None:
        if self._dry_run:
            self.logger.info("DRY RUN: Skipping startup cleanup reconciliation.")
            return

        in_progress = self.db.get_in_progress_cleanups()
        if not in_progress:
            return

        self.logger.info("Reconciling %s IN_PROGRESS cleanups from a previous crash.", len(in_progress))
        
        now = datetime.now(timezone.utc).isoformat()
        
        for record in in_progress:
            mid = record["id"]
            attempt_id = record["attempt_id"]
            expected_hash = record["sha256"]
            source_path = Path(record["original_path"])
            dest_path = Path(record["destination_path"]) if record["destination_path"] else None
            
            source_exists = source_path.is_file()
            dest_exists = dest_path.is_file() if dest_path else False
            
            if source_exists and not dest_exists:
                # Source exists, Destination missing -> ELIGIBLE
                self.db.finish_cleanup_attempt(mid, attempt_id, "UNCERTAIN", "ELIGIBLE", "crash", "Source exists, dest missing on restart", now)
            elif not source_exists and dest_exists:
                # Source missing, Destination exists -> check hash
                actual_hash = sha256_file(dest_path)
                if actual_hash == expected_hash:
                    self.db.finish_cleanup_attempt(mid, attempt_id, "SUCCESS", "CLEANED", finished_at=now)
                else:
                    self.db.finish_cleanup_attempt(mid, attempt_id, "ERROR", "NEEDS_REVIEW", "hash_mismatch", "Dest exists but hash mismatch", now)
            elif source_exists and dest_exists:
                # Both exist -> verify hash
                s_hash = sha256_file(source_path)
                d_hash = sha256_file(dest_path)
                if s_hash == expected_hash and d_hash == expected_hash:
                    try:
                        source_path.unlink()
                        self.db.finish_cleanup_attempt(mid, attempt_id, "SUCCESS", "CLEANED", finished_at=now)
                    except Exception as e:
                        self.db.finish_cleanup_attempt(mid, attempt_id, "ERROR", "FAILED", "unlink_error", str(e), now)
                else:
                    self.db.finish_cleanup_attempt(mid, attempt_id, "ERROR", "NEEDS_REVIEW", "hash_mismatch", "Both exist but hash mismatch", now)
            elif not source_exists and not dest_exists:
                # Neither exists
                self.db.finish_cleanup_attempt(mid, attempt_id, "ERROR", "SOURCE_MISSING", "missing", "Both source and dest missing on restart", now)
            else:
                self.db.finish_cleanup_attempt(mid, attempt_id, "ERROR", "NEEDS_REVIEW", "unknown", "Unknown reconciliation state", now)
                
            # If temp dest exists, it would have a .tmp suffix and we'd ideally clean it up, but 
            # we don't strictly know the exact .tmp filename here since it's generated randomly at runtime.
            # We rely on the system to eventually clear .tmp files or manual intervention if cross-volume crashes.

    def _verify_path_safety(self) -> None:
        if not self.config.cleanup.enabled:
            return
            
        c = self.config.queue.completed
        i_img = self.config.queue.incoming_images
        i_vid = self.config.queue.incoming_videos
        
        try:
            r_c = c.resolve()
            r_img = i_img.resolve()
            r_vid = i_vid.resolve()
        except Exception as e:
            raise CleanupError(f"Path resolution failed: {e}")
            
        if str(r_c).lower() == str(r_img).lower() or str(r_c).lower() == str(r_vid).lower():
            raise CleanupError("Completed directory cannot be the same as an incoming directory")
            
        if str(r_img).lower().startswith(str(r_c).lower() + os.sep) or str(r_vid).lower().startswith(str(r_c).lower() + os.sep):
            raise CleanupError("Incoming directories cannot be nested inside completed directory")
            
        if str(r_c).lower().startswith(str(r_img).lower() + os.sep) or str(r_c).lower().startswith(str(r_vid).lower() + os.sep):
            raise CleanupError("Completed directory cannot be nested inside incoming directories")

    def run_cleanup(self, now_utc: str | None = None) -> None:
        if not self.config.cleanup.enabled:
            self.logger.info("Cleanup is disabled in configuration. Skipping.")
            return
            
        if not self.config.cleanup.verify_hash_before_cleanup:
            raise CleanupError("Configuration Error: verify_hash_before_cleanup MUST be True if cleanup is enabled.")
            
        self._verify_path_safety()
        
        if now_utc is None:
            now_dt = datetime.now(timezone.utc)
        else:
            now_dt = datetime.fromisoformat(now_utc)
            if now_dt.tzinfo is None:
                now_dt = now_dt.replace(tzinfo=timezone.utc)
                
        eligible_before = (now_dt - timedelta(days=self.config.cleanup.backup_safety_days)).isoformat()
        
        candidates = self.db.get_cleanup_candidates(eligible_before)
        if not candidates:
            return
            
        self.logger.info("Found %s cleanup candidates.", len(candidates))
        
        for candidate in candidates:
            self._process_candidate(candidate)

    def _process_candidate(self, candidate: dict) -> None:
        mid = candidate["id"]
        source_path = Path(candidate["original_path"])
        expected_hash = candidate["sha256"]
        short_hash = candidate["short_hash"]
        original_filename = candidate["original_filename"]
        now = datetime.now(timezone.utc).isoformat()
        
        if not source_path.is_file():
            self.logger.warning("Candidate [%s] source file missing", short_hash)
            log_private(self.logger, self.opts.verbose_private, "Candidate [%s] private missing source path: %r", short_hash, str(source_path))
            self.db.finish_cleanup_attempt(mid, None, "ERROR", "SOURCE_MISSING", "missing", "Source file not found")
            return
            
        # Hash verification
        actual_hash = sha256_file(source_path)
        if actual_hash != expected_hash:
            self.logger.warning("Candidate [%s] hash mismatch during cleanup", short_hash)
            log_private(self.logger, self.opts.verbose_private, "Candidate [%s] private hash mismatch: expected %s, got %s", short_hash, expected_hash, actual_hash)
            self.db.finish_cleanup_attempt(mid, None, "ERROR", "SOURCE_CHANGED", "hash_mismatch", "File content changed")
            return
            
        if self.config.cleanup.mode == "move":
            self._do_move(mid, source_path, original_filename, expected_hash, short_hash, actual_hash)
        elif self.config.cleanup.mode == "delete":
            self._do_delete(mid, short_hash, source_path, expected_hash)
        else:
            self.logger.error("Candidate [%s] unknown cleanup mode: %s", short_hash, self.config.cleanup.mode)
            
    def _do_delete(self, mid: int, short_hash: str, source_path: Path, expected_hash: str) -> None:
        if not self.config.cleanup.confirm_permanent_delete:
            self.logger.error("Deletion rejected: confirm_permanent_delete is false")
            return
            
        now = datetime.now(timezone.utc).isoformat()
        if self._dry_run:
            self.logger.info("[DRY RUN] Would delete candidate [%s]", short_hash)
            log_private(self.logger, self.opts.verbose_private, "[DRY RUN] Candidate [%s] private path to delete: %r", short_hash, str(source_path))
            return
            
        attempt_id = self.db.start_cleanup_attempt(mid, "delete", str(source_path), None, now)
        try:
            source_path.unlink()
            now = datetime.now(timezone.utc).isoformat()
            self.db.finish_cleanup_attempt(mid, attempt_id, "SUCCESS", "CLEANED", finished_at=now)
        except Exception as e:
            now = datetime.now(timezone.utc).isoformat()
            self.db.finish_cleanup_attempt(mid, attempt_id, "ERROR", "FAILED", "delete_error", str(e), now)

    def _do_move(self, mid: int, source_path: Path, original_filename: str, expected_hash: str, short_hash: str, actual_hash: str) -> None:
        # Determine subdir based on file type roughly (just using extension for simplicity, or we can use the media.media_type)
        # We don't have media_type in the query, so let's just dump into Completed/
        dest_dir = self.config.queue.completed
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        final_dest = dest_dir / original_filename
        
        # Collision handling
        if final_dest.exists():
            if final_dest.is_file():
                dest_hash = sha256_file(final_dest)
                if dest_hash == expected_hash:
                    # Same hash, valid copy
                    self._remove_source_for_existing_dest(mid, short_hash, source_path, final_dest)
                    return
            
            # Different hash or directory, fallback to short_hash
            final_dest = dest_dir / f"{final_dest.stem}_{short_hash}{final_dest.suffix}"
            if final_dest.exists():
                if final_dest.is_file() and sha256_file(final_dest) == expected_hash:
                    self._remove_source_for_existing_dest(mid, short_hash, source_path, final_dest)
                    return
                # Still collision, use full hash
                final_dest = dest_dir / f"{final_dest.stem}_{expected_hash}{final_dest.suffix}"
                if final_dest.exists():
                    self.logger.error("Candidate [%s] cannot resolve filename collision", short_hash)
                    self.db.finish_cleanup_attempt(mid, None, "ERROR", "FAILED", "collision", "Could not resolve destination filename")
                    return
                    
        now = datetime.now(timezone.utc).isoformat()
        if self._dry_run:
            self.logger.info("[DRY RUN] Would move candidate [%s]", short_hash)
            log_private(self.logger, self.opts.verbose_private, "[DRY RUN] Candidate [%s] private move: %r to %r", short_hash, str(source_path), str(final_dest))
            return
            
        attempt_id = self.db.start_cleanup_attempt(mid, "move", str(source_path), str(final_dest), now)
        
        try:
            # Check if same volume
            try:
                os.rename(source_path, final_dest) # Atomic rename if same volume
            except OSError:
                # Cross-volume
                tmp_dest = final_dest.with_name(final_dest.name + f".{uuid4().hex}.tmp")
                shutil.copy2(source_path, tmp_dest)
                # Verify cross-volume copy
                tmp_hash = sha256_file(tmp_dest)
                if tmp_hash != expected_hash:
                    tmp_dest.unlink()
                    raise RuntimeError("Cross-volume copy verification failed (hash mismatch)")
                if tmp_dest.stat().st_size != source_path.stat().st_size:
                    tmp_dest.unlink()
                    raise RuntimeError("Cross-volume copy verification failed (size mismatch)")
                
                os.rename(tmp_dest, final_dest)
                source_path.unlink()
                
        except Exception as e:
            now = datetime.now(timezone.utc).isoformat()
            self.db.finish_cleanup_attempt(mid, attempt_id, "ERROR", "FAILED", "move_error", str(e), now)
            return
            
        try:
            now = datetime.now(timezone.utc).isoformat()
            self.db.finish_cleanup_attempt(mid, attempt_id, "SUCCESS", "CLEANED", finished_at=now)
        except Exception as e:
            self.logger.error(
                "Candidate [%s] filesystem cleanup completed but DB finalization failed; leaving IN_PROGRESS for reconciliation (%s)",
                short_hash, type(e).__name__
            )

    def _remove_source_for_existing_dest(self, mid: int, short_hash: str, source_path: Path, dest_path: Path) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if self._dry_run:
            self.logger.info("[DRY RUN] Would remove source for candidate [%s] since destination matches hash", short_hash)
            log_private(self.logger, self.opts.verbose_private, "[DRY RUN] Candidate [%s] private remove source %r since dest %r matches hash", short_hash, str(source_path), str(dest_path))
            return
            
        attempt_id = self.db.start_cleanup_attempt(mid, "move_collision", str(source_path), str(dest_path), now)
        try:
            source_path.unlink()
        except Exception as e:
            now = datetime.now(timezone.utc).isoformat()
            self.db.finish_cleanup_attempt(mid, attempt_id, "ERROR", "FAILED", "unlink_error", str(e), now)
            return
            
        try:
            now = datetime.now(timezone.utc).isoformat()
            self.db.finish_cleanup_attempt(mid, attempt_id, "SUCCESS", "CLEANED", finished_at=now)
        except Exception as e:
            self.logger.error(
                "Candidate [%s] filesystem cleanup completed but DB finalization failed; leaving IN_PROGRESS for reconciliation (%s)",
                short_hash, type(e).__name__
            )
