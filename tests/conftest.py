import pytest
from pathlib import Path
from src.config import Config, AppConfig, QueueConfig, TelegramConfig, TelegramTopicsConfig, SecretsConfig, CleanupConfig

def make_test_config(tmp_path: Path) -> Config:
    app = AppConfig(
        dry_run=False,
        database_path=tmp_path / "db.sqlite",
        log_directory=tmp_path / "logs",
        cache_directory=tmp_path / "cache",
        private_data_directory=tmp_path / "private"
    )
    
    queue = QueueConfig(
        incoming_images=tmp_path / "incoming" / "images",
        incoming_videos=tmp_path / "incoming" / "videos",
        completed=tmp_path / "completed",
        failed=tmp_path / "failed",
        stable_seconds=1,
        scan_interval_seconds=300
    )
    
    cleanup = CleanupConfig(
        enabled=False,
        mode="move",
        backup_safety_days=7,
        verify_hash_before_cleanup=True,
        confirm_permanent_delete=False
    )
    
    topics = TelegramTopicsConfig(
        people=1,
        family_groups=2,
        travel_nature=3,
        everyday=6,
        screenshots_documents=5,
        videos=8,
        misc=9
    )
    
    telegram = TelegramConfig(
        group_id="-12345",
        topics=topics,
        caption_max_length=900,
        api_mode="hosted",
        hosted_upload_limit_mb=50,
        local_upload_limit_mb=2000
    )
    
    secrets = SecretsConfig(
        bot_token="token",
        api_id="id",
        api_hash="hash"
    )
    
    from src.config import FaceConfig
    faces = FaceConfig(
        enabled=False,
        analyze_images=True,
        analyze_videos=False,
        use_for_routing=False,
        include_names_in_captions=False,
        calibration_required=True,
        reference_root=tmp_path / "private_data" / "faces" / "references",
        model_root=tmp_path / "private_data" / "faces" / "models",
        detector_model="face_detection_yunet_2023mar.onnx",
        recognizer_model="face_recognition_sface_2021dec.onnx",
        detector_confidence=0.90,
        minimum_face_size_px=96,
        minimum_references_per_person=5,
        minimum_supporting_references=2,
        accept_threshold=None,
        review_threshold=None,
        minimum_margin=None,
        save_debug_crops=False,
        similarity_metric="cosine"
    )
    
    return Config(
        app=app,
        queue=queue,
        cleanup=cleanup,
        faces=faces,
        telegram=telegram,
        secrets=secrets
    )

@pytest.fixture
def test_config(tmp_path: Path) -> Config:
    return make_test_config(tmp_path)
