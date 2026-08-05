import sys; sys.path.insert(0, '')
import traceback, numpy as np, logging, pytest, tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch
from tests.conftest import configure_test_face_policy, activate_scoped_test_calibration
from src.database import ArchiveDatabase
from src.face_analysis import FaceAnalysisWorker

try:
    with tempfile.TemporaryDirectory() as td:
        memory_db = ArchiveDatabase(Path(td) / "test.sqlite3")
        memory_db.apply_migrations(Path("sql"))

        config = MagicMock()
        config.faces.enabled = True
        config.faces.minimum_face_size_px = 50
        config.faces.policy_identity = "mock_policy"
        configure_test_face_policy(config, top_k=1, strong_support=1)

        logger = logging.getLogger("test")
        logger.addHandler(logging.StreamHandler(sys.stdout))
        logger.setLevel(logging.DEBUG)

        mock_engine = MagicMock()
        mock_engine.model_identity.return_value = "modelA"
        
        dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"target")

        person1 = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person1, "r1", "r1.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")

        activate_scoped_test_calibration(memory_db, config, "modelA", ["r1"])

        mock_engine.compare_embeddings.return_value = 0.90

        worker = FaceAnalysisWorker(config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        
        def mock_decode(*args, **kwargs): return {"image": dummy_img}
        with patch("src.face_analysis.decode_image_with_exif", side_effect=mock_decode):
            res = worker.analyze_image(dummy_img)
            print("RESULTS:", res.face_results)
except Exception as e:
    traceback.print_exc()
