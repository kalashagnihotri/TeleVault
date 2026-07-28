from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

class ConfigError(Exception):
    """Raised when there is a configuration error."""

@dataclass(slots=True)
class AppConfig:
    dry_run: bool
    database_path: Path
    log_directory: Path
    cache_directory: Path
    private_data_directory: Path

@dataclass(slots=True)
class QueueConfig:
    incoming_images: Path
    incoming_videos: Path
    completed: Path
    failed: Path
    stable_seconds: int
    scan_interval_seconds: int

@dataclass(slots=True)
class CleanupConfig:
    enabled: bool
    mode: str
    backup_safety_days: int
    verify_hash_before_cleanup: bool
    confirm_permanent_delete: bool

@dataclass(slots=True)
class FaceConfig:
    enabled: bool
    analyze_images: bool
    analyze_videos: bool
    use_for_routing: bool
    include_names_in_captions: bool
    calibration_required: bool
    reference_root: Path
    model_root: Path
    detector_model: str
    recognizer_model: str
    detector_confidence: float
    minimum_face_size_px: int
    minimum_references_per_person: int
    minimum_supporting_references: int
    accept_threshold: float | None
    review_threshold: float | None
    minimum_margin: float | None
    save_debug_crops: bool
    similarity_metric: str

@dataclass(slots=True)
class TelegramTopicsConfig:
    people: int
    family_groups: int
    travel_nature: int
    everyday: int
    screenshots_documents: int
    videos: int
    misc: int

@dataclass(slots=True)
class TelegramConfig:
    group_id: str
    topics: TelegramTopicsConfig
    caption_max_length: int
    api_mode: str
    hosted_upload_limit_mb: int
    local_upload_limit_mb: int

@dataclass(slots=True)
class SecretsConfig:
    bot_token: str
    api_id: str
    api_hash: str

@dataclass(slots=True)
class Config:
    app: AppConfig
    queue: QueueConfig
    cleanup: CleanupConfig
    faces: FaceConfig
    telegram: TelegramConfig
    secrets: SecretsConfig

def _parse_path(val: str) -> Path:
    return Path(val)

def load_config(yaml_path: Path = Path("config/config.yaml")) -> Config:
    load_dotenv()

    if not yaml_path.is_file():
        raise ConfigError(f"Configuration file not found: {yaml_path}")

    with yaml_path.open("r", encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML file: {e}")

    app_data = data.get("app", {})
    queue_data = data.get("queue", {})
    telegram_data = data.get("telegram", {})
    telegram_topics_data = telegram_data.get("topics", {})

    app = AppConfig(
        dry_run=app_data.get("dry_run", True),
        database_path=_parse_path(app_data.get("database_path", "data/archive.sqlite3")),
        log_directory=_parse_path(app_data.get("log_directory", "logs")),
        cache_directory=_parse_path(app_data.get("cache_directory", "cache")),
        private_data_directory=_parse_path(app_data.get("private_data_directory", "private_data")),
    )

    queue = QueueConfig(
        incoming_images=_parse_path(queue_data.get("incoming_images", "incoming/images")),
        incoming_videos=_parse_path(queue_data.get("incoming_videos", "incoming/videos")),
        completed=_parse_path(queue_data.get("completed", "completed")),
        failed=_parse_path(queue_data.get("failed", "failed")),
        stable_seconds=int(queue_data.get("stable_seconds", 60)),
        scan_interval_seconds=int(queue_data.get("scan_interval_seconds", 300)),
    )

    topics = TelegramTopicsConfig(
        people=int(telegram_topics_data.get("people", 0)),
        family_groups=int(telegram_topics_data.get("family_groups", 0)),
        travel_nature=int(telegram_topics_data.get("travel_nature", 0)),
        everyday=int(telegram_topics_data.get("everyday", 0)),
        screenshots_documents=int(telegram_topics_data.get("screenshots_documents", 0)),
        videos=int(telegram_topics_data.get("videos", 0)),
        misc=int(telegram_topics_data.get("misc", 0)),
    )

    telegram = TelegramConfig(
        group_id=str(telegram_data.get("group_id", "0")),
        topics=topics,
        caption_max_length=int(telegram_data.get("caption_max_length", 900)),
        api_mode=str(telegram_data.get("api_mode", "hosted")),
        hosted_upload_limit_mb=int(telegram_data.get("hosted_upload_limit_mb", 50)),
        local_upload_limit_mb=int(telegram_data.get("local_upload_limit_mb", 2000)),
    )

    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")

    if not bot_token:
        bot_token = ""
    if not api_id:
        api_id = ""
    if not api_hash:
        api_hash = ""

    secrets = SecretsConfig(
        bot_token=bot_token,
        api_id=api_id,
        api_hash=api_hash,
    )

    cleanup_data = data.get("cleanup")
    if cleanup_data is None:
        import logging
        logger = logging.getLogger("telegram_media")
        logger.warning("DeprecationWarning: 'cleanup' config block is missing. Falling back to 'queue.cleanup_safety_days'. Cleanup remains disabled.")
        cleanup = CleanupConfig(
            enabled=False,
            mode="move",
            backup_safety_days=int(queue_data.get("cleanup_safety_days", 7)),
            verify_hash_before_cleanup=True,
            confirm_permanent_delete=False,
        )
    else:
        cleanup = CleanupConfig(
            enabled=bool(cleanup_data.get("enabled", False)),
            mode=str(cleanup_data.get("mode", "move")),
            backup_safety_days=int(cleanup_data.get("backup_safety_days", 7)),
            verify_hash_before_cleanup=bool(cleanup_data.get("verify_hash_before_cleanup", True)),
            confirm_permanent_delete=bool(cleanup_data.get("confirm_permanent_delete", False)),
        )

    if cleanup.backup_safety_days < 0:
        raise ConfigError(f"backup_safety_days cannot be negative, got {cleanup.backup_safety_days}")

    if cleanup.enabled and not cleanup.verify_hash_before_cleanup:
        raise ConfigError("verify_hash_before_cleanup must be True when cleanup is enabled")

    # Path validation
    def check_overlap(p1: Path, p2: Path):
        try:
            r1 = p1.resolve()
            r2 = p2.resolve()
        except Exception:
            return False
        return str(r1).lower() == str(r2).lower() or str(r2).lower().startswith(str(r1).lower() + os.sep)

    if check_overlap(queue.completed, queue.incoming_images) or check_overlap(queue.completed, queue.incoming_videos):
        raise ConfigError("Completed directory cannot be the same as or nested inside an incoming directory")
    if check_overlap(queue.incoming_images, queue.completed) or check_overlap(queue.incoming_videos, queue.completed):
        raise ConfigError("Incoming directories cannot be the same as or nested inside the completed directory")

    faces_data = data.get("faces", {})
    faces = FaceConfig(
        enabled=bool(faces_data.get("enabled", False)),
        analyze_images=bool(faces_data.get("analyze_images", True)),
        analyze_videos=bool(faces_data.get("analyze_videos", False)),
        use_for_routing=bool(faces_data.get("use_for_routing", False)),
        include_names_in_captions=bool(faces_data.get("include_names_in_captions", False)),
        calibration_required=bool(faces_data.get("calibration_required", True)),
        reference_root=Path(faces_data.get("reference_root", "private_data/faces/references")),
        model_root=Path(faces_data.get("model_root", "private_data/faces/models")),
        detector_model=str(faces_data.get("detector_model", "face_detection_yunet_2023mar.onnx")),
        recognizer_model=str(faces_data.get("recognizer_model", "face_recognition_sface_2021dec.onnx")),
        detector_confidence=float(faces_data.get("detector_confidence", 0.90)),
        minimum_face_size_px=int(faces_data.get("minimum_face_size_px", 96)),
        minimum_references_per_person=int(faces_data.get("minimum_references_per_person", 5)),
        minimum_supporting_references=int(faces_data.get("minimum_supporting_references", 2)),
        accept_threshold=faces_data.get("accept_threshold"),
        review_threshold=faces_data.get("review_threshold"),
        minimum_margin=faces_data.get("minimum_margin"),
        save_debug_crops=bool(faces_data.get("save_debug_crops", False)),
        similarity_metric=str(faces_data.get("similarity_metric", "cosine")),
    )

    if faces.enabled:
        if faces.similarity_metric != "cosine":
            raise ConfigError(f"similarity_metric must be cosine, got {faces.similarity_metric}")
        
        if faces.accept_threshold is not None and faces.review_threshold is not None:
            if not (0 <= faces.review_threshold < faces.accept_threshold <= 1):
                raise ConfigError(f"Invalid thresholds: must have 0 <= review_threshold < accept_threshold <= 1")
        
        if faces.minimum_margin is not None and faces.minimum_margin <= 0:
            raise ConfigError("minimum_margin must be > 0")

    return Config(app=app, queue=queue, cleanup=cleanup, faces=faces, telegram=telegram, secrets=secrets)
