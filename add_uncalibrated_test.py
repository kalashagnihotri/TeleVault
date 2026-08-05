import os

path = 'tests/test_face_analysis_dry_run.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

new_test = '''

def test_uncalibrated_diagnostic_scores(memory_db, mock_engine_config, tmp_path):
    c1 = MediaCandidate(path=tmp_path / "img1.jpg", media_type="image", size_bytes=100, modified_ns=0, sha256="abcxxxx")

    logger = logging.getLogger("test_uncalibrated")
    logger.addHandler(logging.NullHandler())
    
    mock_engine = MagicMock()
    mock_engine.model_identity.return_value = "modelA"

    dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
    with patch("src.face_analysis.decode_image_with_exif", return_value={"image": dummy_img}):
        mock_engine.detect_faces.return_value = [[0, 0, 100, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]]
        mock_engine.align_face.return_value = "aligned"
        mock_engine.create_embedding.return_value = MagicMock(size=128, tobytes=lambda: b"emb")

        person_id = memory_db.get_or_create_person("person1", "Person 1")
        memory_db.add_reference(person_id, "refhash", "ref.jpg", 0.99, 100, 100, "{}", np.ones(128, dtype=np.float32).tobytes(), 128, "modelA")
        
        # No calibration activated

        mock_engine.compare_embeddings.return_value = 0.95

        worker = FaceAnalysisWorker(mock_engine_config, memory_db, mock_engine, logger)
        worker.load_snapshots()
        res = worker.analyze_image(dummy_img)

        assert len(res.face_results) == 1
        face = res.face_results[0]
        
        assert face["decision"] == "UNKNOWN_UNCALIBRATED"
        assert face["best_person_id"] == person_id
        assert face["best_score"] == 0.95
        assert res.accepted_faces == 0
        
        # Ensure no database writes
        with memory_db.connect() as conn:
            assert conn.execute("SELECT COUNT(*) FROM face_calibrations").fetchone()[0] == 0
            # face_results are not written by FaceAnalysisWorker directly in this test, but just making sure
'''

content += new_test
with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
