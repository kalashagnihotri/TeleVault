from __future__ import annotations

import logging
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from src.config import Config
from src.database import ArchiveDatabase
from src.file_stability import is_supported_candidate
from src.hashing import sha256_file
from src.models import MediaCandidate
from src.places import PlaceResolver
from src.metadata_image import extract_image_metadata
from src.metadata_video import extract_video_metadata
from src.routing import choose_topic, RouteInput
from src.captions import build_caption
from src.logging_utils import RuntimeOptions, ProcessingStage, safe_candidate_id, log_private

class QueueScanner:
    def __init__(self, config: Config, db: ArchiveDatabase, logger: logging.Logger, opts: RuntimeOptions | None = None) -> None:
        self.config = config
        self.db = db
        self.logger = logger
        self.opts = opts or RuntimeOptions()
        
        self.queue_dirs = [
            self.config.queue.incoming_images,
            self.config.queue.incoming_videos
        ]
        
        for d in self.queue_dirs:
            d.mkdir(parents=True, exist_ok=True)
            
        self.config.queue.completed.mkdir(parents=True, exist_ok=True)
        self.config.queue.failed.mkdir(parents=True, exist_ok=True)
        
        self.place_resolver = PlaceResolver()

    def scan_once(self) -> list[MediaCandidate]:
        self.logger.info("Starting queue scan.")
        candidates_initial = {}
        
        for queue_dir in self.queue_dirs:
            if not queue_dir.exists():
                continue
            
            for path in queue_dir.rglob("*"):
                if not is_supported_candidate(path):
                    continue
                try:
                    stat = path.stat()
                    if stat.st_size > 0:
                        candidates_initial[path] = (stat.st_size, stat.st_mtime_ns)
                except OSError as e:
                    self.logger.warning("Could not stat a discovered file: error=%s", type(e).__name__)
                    log_private(self.logger, self.opts.verbose_private, "Stat error on path=%r", str(path), exc_info=True)

        if not candidates_initial:
            self.logger.info("Finished queue scan.")
            return []

        if self.config.queue.stable_seconds > 0:
            self.logger.info("Waiting %ss for files to stabilize...", self.config.queue.stable_seconds)
            time.sleep(self.config.queue.stable_seconds)

        processed_candidates = []
        # Sort deterministically
        sorted_paths = sorted(candidates_initial.keys(), key=lambda p: str(p).lower())
        for path in sorted_paths:
            prev_size, prev_time = candidates_initial[path]
            try:
                curr_stat = path.stat()
            except OSError:
                self.logger.warning("A file disappeared before processing")
                log_private(self.logger, self.opts.verbose_private, "File disappeared: %r", str(path))
                continue

            if curr_stat.st_size == prev_size and curr_stat.st_mtime_ns == prev_time:
                try:
                    with path.open("rb"):
                        pass
                    candidate = self.process_file(path, curr_stat.st_size, curr_stat.st_mtime_ns, fallback_index=len(processed_candidates) + 1)
                    if candidate:
                        processed_candidates.append(candidate)
                except OSError as e:
                    self.logger.warning("A file is not readable, skipping: error=%s", type(e).__name__)
                    log_private(self.logger, self.opts.verbose_private, "File not readable path=%r", str(path), exc_info=True)
            else:
                self.logger.warning("A file is not stable, skipping for now")
                log_private(self.logger, self.opts.verbose_private, "File not stable path=%r", str(path))

        self.logger.info("Finished queue scan.")
        return processed_candidates

    def process_file(self, path: Path, size_bytes: int, modified_ns: int, fallback_index: int = 1) -> MediaCandidate | None:
        # Discovered logged after hashing now

        ext = path.suffix.lower()
        if ext in {".jpg", ".jpeg", ".png", ".webp"}:
            media_type = "image"
        elif ext in {".mp4", ".mov", ".mkv", ".webm"}:
            media_type = "video"
        else:
            media_type = "other"

        candidate = MediaCandidate(
            path=path,
            media_type=media_type,
            size_bytes=size_bytes,
            modified_ns=modified_ns
        )

        try:
            digest = sha256_file(candidate.path)
        except Exception as e:
            candidate_id = safe_candidate_id(None, fallback_number=fallback_index)
            self.logger.error("Candidate [%s] failed: stage=%s error=%s", candidate_id, ProcessingStage.HASH.value, type(e).__name__)
            log_private(self.logger, self.opts.verbose_private, "Candidate [%s] private HASH failure: path=%r", candidate_id, str(path), exc_info=True)
            return None

        candidate.sha256 = digest
        short_hash = safe_candidate_id(digest)
        self.logger.info("Discovered candidate [%s]", short_hash)
        log_private(self.logger, self.opts.verbose_private, "Candidate [%s] private source: filename=%r path=%r full_sha256=%s", short_hash, path.name, str(path), digest)
        timestamp = datetime.now(timezone.utc).isoformat()
        
        meta = self._extract_metadata(candidate)
        topic = self._route(candidate.media_type, meta)
        candidate.metadata = meta
        candidate.proposed_route = topic

        with self.db.connect() as conn:
            existing = conn.execute("SELECT id, state FROM media WHERE sha256 = ?", (digest,)).fetchone()
            
        if existing:
            candidate.is_duplicate = True
            candidate.media_id = existing["id"]
            if self.config.app.dry_run:
                self.logger.info("[DRY RUN] Candidate [%s] already in database (state: %s)", short_hash, existing['state'])
                gps_str = f"Lat: {round(meta.latitude, 4)}, Lon: {round(meta.longitude, 4)}" if meta.has_gps else "None"
                self.logger.info("[DRY RUN] Candidate [%s] metadata -> GPS present: %s, Coords: %s, Location: %s, Route: %s", short_hash, meta.has_gps, gps_str, meta.location_label, topic)
                return candidate
            else:
                self.logger.info("Candidate [%s] duplicate hash detected, already in database", short_hash)
                return candidate

        if self.config.app.dry_run:
            self.logger.info("[DRY RUN] Would reserve candidate [%s]", short_hash)
            gps_str = f"Lat: {round(meta.latitude, 4)}, Lon: {round(meta.longitude, 4)}" if meta.has_gps else "None"
            self.logger.info("[DRY RUN] Candidate [%s] metadata -> GPS present: %s, Coords: %s, Location: %s, Route: %s", short_hash, meta.has_gps, gps_str, meta.location_label, topic)
            return candidate

        media_id = self.db.reserve_media(
            sha256=digest,
            short_hash=short_hash,
            original_path=str(candidate.path),
            original_filename=candidate.path.name,
            media_type=candidate.media_type,
            size_bytes=candidate.size_bytes,
            modified_ns=candidate.modified_ns,
            state="RESERVED",
            timestamp=timestamp
        )

        if media_id is None:
            self.logger.info("Candidate [%s] duplicate hash detected, already in database", short_hash)
            candidate.is_duplicate = True
            return candidate
            
        candidate.media_id = media_id
        self.logger.info("Candidate [%s] reserved as media %s. Extracting metadata...", short_hash, media_id)
        
        caption = build_caption(
            date_text=meta.date_taken or "Unknown Date",
            location=meta.location_label,
            people=[],
            labels=[],
            filename=candidate.path.name,
            short_hash=short_hash,
            max_length=self.config.telegram.caption_max_length
        )
        
        scene_state = "SKIPPED"
        if candidate.media_type == "image":
            if getattr(self.config, "scenes", None) and self.config.scenes.enabled:
                scene_state = "PENDING"

        self.db.update_metadata(
            media_id=media_id,
            date_taken=meta.date_taken,
            has_gps=1 if meta.has_gps else 0,
            location_label=meta.location_label,
            people_json="[]",
            labels_json="[]",
            route_key=topic,
            state="READY_TO_UPLOAD",
            timestamp=datetime.now(timezone.utc).isoformat(),
            scene_state=scene_state
        )
        self.logger.info("Candidate [%s] metadata and routing complete. State: READY_TO_UPLOAD.", short_hash)
        return candidate

    def _extract_metadata(self, candidate: MediaCandidate):
        if candidate.media_type == "image":
            meta = extract_image_metadata(candidate.path, opts=self.opts)
        elif candidate.media_type == "video":
            meta = extract_video_metadata(candidate.path, opts=self.opts)
        else:
            meta = extract_image_metadata(candidate.path, opts=self.opts) # fallback
            
        meta.location_label = self.place_resolver.resolve(meta.latitude, meta.longitude)
        
        if not meta.date_taken:
            dt = datetime.fromtimestamp(candidate.modified_ns / 1e9, tz=timezone.utc)
            meta.date_taken = dt.isoformat()
            
        return meta
        
    def _route(self, media_type: str, meta) -> str:
        input_data = RouteInput(
            media_type=media_type,
            people=tuple(),
            labels=tuple(),
            has_gps=meta.has_gps
        )
        return choose_topic(input_data)
