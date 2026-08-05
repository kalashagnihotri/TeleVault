import sys
sys.path.insert(0, '')
from unittest.mock import MagicMock
from src.face_analysis import FaceAnalysisWorker
import numpy as np

mock_engine = MagicMock()
mock_engine.compare_embeddings.return_value = 0.90

worker = FaceAnalysisWorker(MagicMock(), MagicMock(), mock_engine, MagicMock())
worker.ref_snapshot = [{"person_id": 1, "embedding": b"emb1"}]

try:
    worker._calculate_person_scores(b"target", top_k=3)
except Exception as e:
    import traceback
    traceback.print_exc()
