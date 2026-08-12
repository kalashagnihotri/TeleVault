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
    
    from src.config import FaceConfig, SceneConfig
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
        low_resolution_min_face_size_px=48,
        low_resolution_detector_confidence=0.90,
        low_resolution_accept_threshold_boost=0.04,
        low_resolution_margin_boost=0.03,
        low_resolution_individual_support_boost=0.04,
        low_resolution_minimum_strong_support=3,
        minimum_references_per_person=5,
        aggregate_method="top_k_mean",
        aggregate_top_k=3,
        minimum_strong_support=2,
        aggregate_accept_threshold=None,
        aggregate_review_threshold=None,
        individual_strong_support_threshold=None,
        minimum_aggregate_margin=None,
        save_debug_crops=False,
        similarity_metric="cosine"
    )
    
    scenes = SceneConfig(
        enabled=True,
        model_path="",
        minimum_confidence=0.25,
        max_labels=3,
        enable_screenshot_heuristics=True,
        enable_document_heuristics=True
    )

    return Config(
        app=app,
        queue=queue,
        cleanup=cleanup,
        faces=faces,
        scenes=scenes,
        telegram=telegram,
        secrets=secrets
    )

@pytest.fixture
def test_config(tmp_path: Path) -> Config:
    return make_test_config(tmp_path)

def configure_test_face_policy(config: Config, top_k: int = 1, strong_support: int = 1) -> None:
    config.faces.aggregate_method = "top_k_mean"
    config.faces.aggregate_top_k = top_k
    config.faces.minimum_strong_support = strong_support
    config.faces.policy_identity = (
        f"top_k_mean:k={top_k}:strong_support={strong_support}:"
        f"lr_min={config.faces.low_resolution_min_face_size_px}:"
        f"lr_conf={config.faces.low_resolution_detector_confidence}:"
        f"lr_ab={config.faces.low_resolution_accept_boost}:"
        f"lr_mb={config.faces.low_resolution_margin_boost}:"
        f"lr_ib={config.faces.low_resolution_individual_support_boost}:"
        f"lr_ms={config.faces.low_resolution_minimum_strong_support}:"
        f"policy_v=2"
    )
    config.faces.aggregate_accept_threshold = 0.8
    config.faces.aggregate_review_threshold = 0.6
    config.faces.minimum_aggregate_margin = 0.1
    config.faces.individual_strong_support_threshold = 0.75

def activate_scoped_test_calibration(
    db,
    config: Config,
    model_identity: str,
    reference_hashes: list[str],
    accept_threshold: float = 0.8,
    review_threshold: float = 0.6,
    minimum_margin: float = 0.1,
    individual_strong_support_threshold: float = 0.75
) -> str:
    import hashlib
    from src.hashing import get_calibration_scope_hash
    
    # Calculate base reference hash from sorted source hashes
    base_ref_hash = hashlib.sha256(
        "".join(sorted(reference_hashes)).encode("utf-8")
    ).hexdigest()
    
    # Get the policy scoped hash
    policy_hash = get_calibration_scope_hash(
        model_identity=model_identity,
        base_reference_set_hash=base_ref_hash,
        policy_identity=config.faces.policy_identity
    )
    
    # Activate calibration through the database method
    db.activate_calibration(
        model_identity=model_identity,
        reference_set_hash=policy_hash,
        accept_threshold=accept_threshold,
        review_threshold=review_threshold,
        minimum_margin=minimum_margin,
        individual_strong_support_threshold=individual_strong_support_threshold,
        positive_pair_count=0,
        negative_pair_count=0,
        report_json="{}"
    )
    
    print(f"ACTIVATE: base={base_ref_hash} policy={config.faces.policy_identity} ref_set={policy_hash}"); return policy_hash
