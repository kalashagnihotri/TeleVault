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

class QueueScanner:
    def __init__(self, config: Config, db: ArchiveDatabase, logger: logging.Logger) -> None:
        self.config = config
        self.db = db
        self.logger = logger
        
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
                    self.logger.warning(f"Could not stat discovered file {path.name}: {e}")

        if not candidates_initial:
            self.logger.info("Finished queue scan.")
            return []

        if self.config.queue.stable_seconds > 0:
            self.logger.info(f"Waiting {self.config.queue.stable_seconds}s for files to stabilize...")
            time.sleep(self.config.queue.stable_seconds)

        processed_candidates = []
        # Sort deterministically
        sorted_paths = sorted(candidates_initial.keys(), key=lambda p: str(p).lower())
        for path in sorted_paths:
            prev_size, prev_time = candidates_initial[path]
            try:
                curr_stat = path.stat()
            except OSError:
                self.logger.warning(f"File disappeared before processing: {path.name}")
                continue

            if curr_stat.st_size == prev_size and curr_stat.st_mtime_ns == prev_time:
                try:
                    with path.open("rb"):
                        pass
                    candidate = self.process_file(path, curr_stat.st_size, curr_stat.st_mtime_ns)
                    if candidate:
                        processed_candidates.append(candidate)
                except OSError as e:
                    self.logger.warning(f"File not readable, skipping: {path.name} ({e})")
            else:
                self.logger.warning(f"File not stable, skipping for now: {path.name}")

        self.logger.info("Finished queue scan.")
        return processed_candidates

    def process_file(self, path: Path, size_bytes: int, modified_ns: int) -> MediaCandidate | None:
        self.logger.info(f"Discovered candidate: {path.name}")

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
            self.logger.error(f"Failed to hash {candidate.path.name}: {e}")
            return None

        candidate.sha256 = digest
        short_hash = digest[:8]
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
                self.logger.info(f"[DRY RUN] Hash {digest} already in database (state: {existing['state']})")
                gps_str = f"Lat: {round(meta.latitude, 4)}, Lon: {round(meta.longitude, 4)}" if meta.has_gps else "None"
                self.logger.info(f"[DRY RUN] Metadata -> GPS present: {meta.has_gps}, Coords: {gps_str}, Location: {meta.location_label}, Route: {topic}")
                return candidate
            else:
                self.logger.info(f"Duplicate hash detected, already in database: {digest}")
                return candidate

        if self.config.app.dry_run:
            self.logger.info(f"[DRY RUN] Would reserve hash {digest} for {candidate.path.name}")
            gps_str = f"Lat: {round(meta.latitude, 4)}, Lon: {round(meta.longitude, 4)}" if meta.has_gps else "None"
            self.logger.info(f"[DRY RUN] Metadata -> GPS present: {meta.has_gps}, Coords: {gps_str}, Location: {meta.location_label}, Route: {topic}")
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
            self.logger.info(f"Duplicate hash detected, already in database: {digest}")
            candidate.is_duplicate = True
            return candidate
            
        candidate.media_id = media_id
        self.logger.info(f"Reserved media {media_id}. Extracting metadata...")
        
        caption = build_caption(
            date_text=meta.date_taken or "Unknown Date",
            location=meta.location_label,
            people=[],
            labels=[],
            filename=candidate.path.name,
            short_hash=short_hash,
            max_length=self.config.telegram.caption_max_length
        )
        
        self.db.update_metadata(
            media_id=media_id,
            date_taken=meta.date_taken,
            has_gps=1 if meta.has_gps else 0,
            location_label=meta.location_label,
            people_json="[]",
            labels_json="[]",
            route_key=topic,
            state="READY_TO_UPLOAD",
            timestamp=datetime.now(timezone.utc).isoformat()
        )
        self.logger.info(f"Media {media_id} metadata and routing complete. State: READY_TO_UPLOAD.")
        return candidate

    def _extract_metadata(self, candidate: MediaCandidate):
        if candidate.media_type == "image":
            meta = extract_image_metadata(candidate.path)
        elif candidate.media_type == "video":
            meta = extract_video_metadata(candidate.path)
        else:
            meta = extract_image_metadata(candidate.path) # fallback
            
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
