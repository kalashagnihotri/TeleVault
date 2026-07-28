import asyncio
import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

from src.config import Config
from src.database import ArchiveDatabase
from src.telegram_client import TelegramClient
from src.preview import generate_image_preview, generate_video_thumbnail
from src.captions import build_caption

class ConfigurationError(Exception):
    pass

class ArchiveUploader:
    def __init__(self, config: Config, db: ArchiveDatabase, telegram: TelegramClient, logger: logging.Logger):
        self.config = config
        self.db = db
        self.telegram = telegram
        self.logger = logger
        self.cache_dir = self.config.app.cache_dir if hasattr(self.config.app, "cache_dir") else self.config.app.cache_directory
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    async def upload_once(self) -> None:
        self.logger.info("Starting uploader.")
        now = datetime.now(timezone.utc).isoformat()
        
        if not self.config.app.dry_run:
            self.db.mark_uncertain_uploads_needs_review(now)
            
        uploads = self.db.get_pending_uploads(now, limit=50)
        
        for media in uploads:
            try:
                await self._process_media(media)
            except ConfigurationError as e:
                self.logger.error(f"Global configuration error: {e}. Stopping uploads.")
                break
            except Exception as e:
                self.logger.exception(f"Unexpected error processing media {media['id']}: {e}")
                
        self.logger.info("Finished uploader.")

    async def _process_media(self, media) -> None:
        state = media["state"]
        retry_stage = media["retry_stage"]
        
        # Resolve numeric IDs before attempting upload
        route_key = media["route_key"]
        if not route_key:
            route_key = "misc"
            
        if not hasattr(self.config.telegram.topics, route_key):
            now = datetime.now(timezone.utc).isoformat()
            self.db.update_state(media["id"], "CONFIGURATION_ERROR", now)
            self.db.finish_upload_attempt_error(
                media["id"], -1, "CONFIGURATION_ERROR", "invalid_route", 400,
                "invalid_route", f"Unknown route key: {route_key}", None, None, now
            )
            return

        topic_id = getattr(self.config.telegram.topics, route_key, 0)
        group_id_str = self.config.telegram.group_id
        
        try:
            group_id = int(group_id_str)
            if group_id == 0:
                raise ValueError("group_id cannot be 0")
            if not isinstance(topic_id, int) or topic_id < 0:
                raise ValueError("topic_id must be a positive integer")
        except (ValueError, TypeError) as e:
            now = datetime.now(timezone.utc).isoformat()
            self.db.update_state(media["id"], "CONFIGURATION_ERROR", now)
            self.db.finish_upload_attempt_error(
                media["id"], -1, "CONFIGURATION_ERROR", "invalid_config", 400,
                "invalid_config", str(e), None, None, now
            )
            return
            
        media_dict = dict(media)
        media_dict["group_id"] = str(group_id)
        media_dict["topic_id"] = str(topic_id)
        
        if state == "RETRY_WAIT" and retry_stage:
            if retry_stage == "preview":
                state = "READY_TO_UPLOAD"
            elif retry_stage == "original":
                state = "PREVIEW_CONFIRMED"
            elif retry_stage == "original_only":
                state = "READY_TO_UPLOAD"
        
        if state == "READY_TO_UPLOAD":
            await self._handle_preview(media_dict, retry_stage == "original_only")
        elif state == "PREVIEW_CONFIRMED":
            await self._handle_original(media_dict, has_preview=True)

    def _check_size_limit(self, size_bytes: int) -> str | None:
        mb = size_bytes / (1024 * 1024)
        if self.config.telegram.api_mode == "hosted":
            if mb > self.config.telegram.hosted_upload_limit_mb:
                return "NEEDS_LOCAL_API"
        else:
            if mb > self.config.telegram.local_upload_limit_mb:
                return "OVERSIZED_UNSUPPORTED"
        return None

    async def _handle_preview(self, media, force_original_only: bool) -> None:
        size_limit_error = self._check_size_limit(media["size_bytes"])
        if size_limit_error:
            self.logger.info(f"Media {media['id']} fails size limits: {size_limit_error}")
            if not self.config.app.dry_run:
                self.db.update_state(media["id"], size_limit_error, datetime.now(timezone.utc).isoformat())
            return

        original_path = Path(media["original_path"])
        preview_path = self.cache_dir / f"preview_{media['id']}.jpg"
        
        preview_success = False
        if not force_original_only:
            if media["media_type"] == "image":
                preview_success = generate_image_preview(original_path, preview_path)
            elif media["media_type"] == "video":
                preview_success = generate_video_thumbnail(original_path, preview_path)

        if not preview_success:
            self.logger.info(f"Preview generation failed or skipped for {media['id']}. Falling back to original only.")
            await self._handle_original(media, has_preview=False)
            return

        people_names = []
        if self.config.faces.enabled and self.config.faces.include_names_in_captions:
            people_names = self.db.get_media_people_names(media["id"])
            
        caption = build_caption(
            date_text=media["date_taken"] or "Unknown Date",
            location=media["location_label"] or "Misc",
            people=people_names,
            labels=[],
            filename=media["original_filename"],
            short_hash=media["short_hash"],
            max_length=self.config.telegram.caption_max_length
        )

        now = datetime.now(timezone.utc).isoformat()
        if self.config.app.dry_run:
            self.logger.info(f"[DRY RUN] Would send preview for {media['id']} to {media['group_id']}/{media['topic_id']}")
            if preview_path.exists():
                preview_path.unlink()
            return

        attempt_id = self.db.start_upload_attempt(
            media["id"], "preview", "PREVIEW_UPLOADING", 
            preview_path.name, preview_path.stat().st_size,
            media["group_id"], media["topic_id"], now
        )

        try:
            result = await self.telegram.send_photo_preview(
                chat_id=int(media["group_id"]),
                topic_id=int(media["topic_id"]) if media["topic_id"] and media["topic_id"] != 'misc' else 0,
                photo_path=preview_path,
                caption=caption
            )
            
            # success
            now = datetime.now(timezone.utc).isoformat()
            self.db.finish_upload_attempt_success(
                media["id"], attempt_id, "PREVIEW_CONFIRMED",
                str(result.message_id), None, now, is_preview=True
            )
            
            # Immediately chain original
            media_dict = dict(media)
            media_dict["preview_message_id"] = str(result.message_id)
            await self._handle_original(media_dict, has_preview=True)
            
        except asyncio.TimeoutError:
            self.logger.warning(f"Timeout uploading preview for {media['id']}")
            now = datetime.now(timezone.utc).isoformat()
            self.db.finish_upload_attempt_error(
                media["id"], attempt_id, "NEEDS_REVIEW", "timeout", None,
                "timeout", "Network timeout", None, None, now
            )
        except RuntimeError as e:
            self._handle_api_error(e, media["id"], attempt_id, "preview", "READY_TO_UPLOAD")
        except Exception as e:
            self.logger.error(f"Error uploading preview for {media['id']}: {e}")
            now = datetime.now(timezone.utc).isoformat()
            self.db.finish_upload_attempt_error(
                media["id"], attempt_id, "NEEDS_REVIEW", "error", None,
                "unknown", str(e), None, None, now
            )
        finally:
            if preview_path.exists():
                preview_path.unlink()

    async def _handle_original(self, media, has_preview: bool) -> None:
        original_path = Path(media["original_path"])
        
        reply_to = int(media["preview_message_id"]) if has_preview and media["preview_message_id"] else 0
        
        now = datetime.now(timezone.utc).isoformat()
        if self.config.app.dry_run:
            self.logger.info(f"[DRY RUN] Would send original for {media['id']} (reply_to={reply_to})")
            return

        attempt_type = "original" if has_preview else "original_only"
        attempt_id = self.db.start_upload_attempt(
            media["id"], attempt_type, "ORIGINAL_UPLOADING",
            original_path.name, original_path.stat().st_size,
            media["group_id"], media["topic_id"], now
        )

        # If no preview, we attach caption to document
        caption = None
        if not has_preview:
            people_names = []
            if self.config.faces.enabled and self.config.faces.include_names_in_captions:
                people_names = self.db.get_media_people_names(media["id"])
                
            caption = build_caption(
                date_text=media["date_taken"] or "Unknown Date",
                location=media["location_label"] or "Misc",
                people=people_names,
                labels=[],
                filename=media["original_filename"],
                short_hash=media["short_hash"],
                max_length=self.config.telegram.caption_max_length
            )

        try:
            result = await self.telegram.send_original_document(
                chat_id=int(media["group_id"]),
                topic_id=int(media["topic_id"]) if media["topic_id"] and media["topic_id"] != 'misc' else 0,
                original_path=original_path,
                reply_to_message_id=reply_to if reply_to > 0 else None,
                caption=caption
            )
            
            now = datetime.now(timezone.utc).isoformat()
            file_id = result.raw["document"]["file_id"]
            self.db.finish_upload_attempt_success(
                media["id"], attempt_id, "BACKED_UP",
                str(result.message_id), file_id, now, is_preview=False
            )
        except asyncio.TimeoutError:
            self.logger.warning(f"Timeout uploading original for {media['id']}")
            now = datetime.now(timezone.utc).isoformat()
            self.db.finish_upload_attempt_error(
                media["id"], attempt_id, "NEEDS_REVIEW", "timeout", None,
                "timeout", "Network timeout", None, None, now
            )
        except RuntimeError as e:
            fallback = "PREVIEW_CONFIRMED" if has_preview else "READY_TO_UPLOAD"
            self._handle_api_error(e, media["id"], attempt_id, attempt_type, fallback)
        except Exception as e:
            self.logger.error(f"Error uploading original for {media['id']}: {e}")
            now = datetime.now(timezone.utc).isoformat()
            self.db.finish_upload_attempt_error(
                media["id"], attempt_id, "NEEDS_REVIEW", "error", None,
                "unknown", str(e), None, None, now
            )

    def _handle_api_error(self, e: RuntimeError, media_id: int, attempt_id: int, stage: str, fallback_state: str):
        error_msg = str(e)
        now = datetime.now(timezone.utc).isoformat()
        
        # Parse 429
        if "429" in error_msg:
            match = re.search(r"retry after (\d+)", error_msg, re.IGNORECASE)
            delay = int(match.group(1)) if match else 60
            next_retry = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
            self.db.finish_upload_attempt_error(
                media_id, attempt_id, "RETRY_WAIT", "rate_limit", 429,
                "429", error_msg, next_retry, stage, now
            )
            return
            
        # Parse fatal config errors
        fatal_errors = ["Unauthorized", "Bad Request: chat not found", "bot was kicked", "rights"]
        if any(f in error_msg for f in fatal_errors):
            self.db.finish_upload_attempt_error(
                media_id, attempt_id, "CONFIGURATION_ERROR", "config_error", 400,
                "config", error_msg, None, None, now
            )
            raise ConfigurationError(error_msg)
            
        # Parse topic deleted
        if "message thread not found" in error_msg.lower():
            self.db.finish_upload_attempt_error(
                media_id, attempt_id, "CONFIGURATION_ERROR", "invalid_topic", 400,
                "invalid_topic", error_msg, None, None, now
            )
            return
            
        # Other unknown errors
        self.db.finish_upload_attempt_error(
            media_id, attempt_id, fallback_state, "error", None,
            "api_error", error_msg, None, stage, now
        )
