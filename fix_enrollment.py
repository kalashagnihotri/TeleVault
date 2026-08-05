import re

path = 'tests/test_face_enrollment_dry_run.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix mock_engine_config in test_face_enrollment_dry_run.py
c1 = '''@pytest.fixture
def mock_engine_config():
    config = MagicMock()
    config.faces.policy_identity = "mock_policy"
    config.faces.aggregate_top_k = 3
    config.faces.minimum_strong_support = 2
    return config'''
r1 = '''@pytest.fixture
def mock_engine_config():
    from tests.conftest import configure_test_face_policy
    config = MagicMock()
    config.faces.policy_identity = "mock_policy"
    configure_test_face_policy(config, top_k=3, strong_support=2)
    config.faces.minimum_references_per_person = 3
    return config'''
content = content.replace(c1, r1)

# Ensure args have all attributes needed
# We already did args.negatives_dir = None, args.allow_failed_holdout = False earlier, let's verify commit
c2 = '''    args = MagicMock()
    args.negatives_dir = None
    args.allow_failed_holdout = False'''
r2 = '''    args = MagicMock()
    args.negatives_dir = None
    args.allow_failed_holdout = False
    args.commit = False'''
content = content.replace(c2, r2)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)
