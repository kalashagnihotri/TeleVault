import os

path = 'tests/conftest.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

helpers_code = '''
def configure_test_face_policy(config: Config, top_k: int = 1, strong_support: int = 1) -> None:
    config.faces.aggregate_method = "top_k_mean"
    config.faces.aggregate_top_k = top_k
    config.faces.minimum_strong_support = strong_support
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
        "\n".join(sorted(reference_hashes)).encode("utf-8")
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
    
    return policy_hash
'''

if 'def configure_test_face_policy' not in c:
    c += helpers_code

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
