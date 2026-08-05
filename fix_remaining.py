import os, re

# Fix test_face_engine.py
path1 = 'tests/test_face_engine.py'
with open(path1, 'r', encoding='utf-8') as f:
    c1 = f.read()
c1 = c1.replace('config.faces.accept_threshold = 0.8', 'config.faces.aggregate_accept_threshold = 0.8')
c1 = c1.replace('config.faces.review_threshold = 0.6', 'config.faces.aggregate_review_threshold = 0.6')
c1 = c1.replace('config.faces.minimum_margin = 0.1', 'config.faces.minimum_aggregate_margin = 0.1')
c1 = c1.replace('config.faces.accept_threshold = 1.1', 'config.faces.aggregate_accept_threshold = 1.1')
c1 = c1.replace('config.faces.accept_threshold = -0.1', 'config.faces.aggregate_accept_threshold = -0.1')
c1 = c1.replace('config.faces.review_threshold = 0.9', 'config.faces.aggregate_review_threshold = 0.9')
c1 = c1.replace('config.faces.minimum_margin = -0.1', 'config.faces.minimum_aggregate_margin = -0.1')
with open(path1, 'w', encoding='utf-8') as f:
    f.write(c1)

# Fix test_migration_007.py
path2 = 'tests/test_migration_007.py'
with open(path2, 'r', encoding='utf-8') as f:
    c2 = f.read()
c2 = c2.replace("''now''", "datetime('now')")
with open(path2, 'w', encoding='utf-8') as f:
    f.write(c2)

# Fix test_optional_dependencies.py
path3 = 'tests/test_optional_dependencies.py'
with open(path3, 'r', encoding='utf-8') as f:
    c3 = f.read()
# We need to make mock_load_config return a config with no G:\ paths.
# Best way is to use a MagicMock or modify app.database_path etc.
# Actually, the problem is original_load_config() hits the real config which has G:\.
# We can just mock load_config to return a simple mock config.
# Wait, it needs to be valid enough for main.py to not crash before it exits.
patch_str = '''def mock_load_config():
    from src.config import Config, AppConfig, FaceConfig, TelegramConfig, SecretsConfig, TopicsConfig
    import pathlib
    c = Config(
        app=AppConfig(dry_run=True, database_path=pathlib.Path("test.db")),
        queue=None,
        cleanup=None,
        faces=FaceConfig(enabled=True, reference_root=pathlib.Path(""), model_root=pathlib.Path(""), detector_model="", recognizer_model="", detector_confidence=0.9, minimum_face_size_px=50, minimum_references_per_person=2, aggregate_method="top_k_mean", aggregate_top_k=3, minimum_strong_support=2),
        telegram=TelegramConfig(group_id=-1, topics=TopicsConfig(face_review=1)),
        secrets=SecretsConfig(bot_token="", api_id="", api_hash="")
    )
    return c'''
c3 = re.sub(r'def mock_load_config\(\):.*?return config', patch_str, c3, flags=re.DOTALL)
# Also for the other test
patch_str2 = patch_str.replace('enabled=True', 'enabled=False')
# wait, there are two functions mock_load_config in c3, one sets enabled=True, one sets enabled=False.
c3 = c3.replace('''def mock_load_config():
        config = original_load_config()
        config.faces.enabled = True
        return config''', patch_str.replace('\n', '\n    '))
c3 = c3.replace('''def mock_load_config():
        config = original_load_config()
        config.faces.enabled = False
        return config''', patch_str2.replace('\n', '\n    '))

with open(path3, 'w', encoding='utf-8') as f:
    f.write(c3)
