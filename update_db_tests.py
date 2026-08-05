import os

path = 'tests/test_face_database.py'
with open(path, 'r', encoding='utf-8') as file:
    content = file.read()

content = content.replace(
    'db.activate_calibration("model_1", "hash_1", 0.8, 0.7, 0.1, 10, 10, "{}")',
    'db.activate_calibration(model_identity="model_1", reference_set_hash="hash_1", accept_threshold=0.8, review_threshold=0.7, minimum_margin=0.1, individual_strong_support_threshold=0.75, positive_pair_count=10, negative_pair_count=10, report_json="{}")'
)

content = content.replace(
    'db.activate_calibration("model_1", "hash_2", 0.85, 0.75, 0.1, 20, 20, "{}")',
    'db.activate_calibration(model_identity="model_1", reference_set_hash="hash_2", accept_threshold=0.85, review_threshold=0.75, minimum_margin=0.1, individual_strong_support_threshold=0.8, positive_pair_count=20, negative_pair_count=20, report_json="{}")'
)

content = content.replace(
    'db.activate_calibration("model_1", "ref_hash", 0.8, 0.7, 0.1, 10, 10, "{}")',
    'db.activate_calibration(model_identity="model_1", reference_set_hash="ref_hash", accept_threshold=0.8, review_threshold=0.7, minimum_margin=0.1, individual_strong_support_threshold=0.75, positive_pair_count=10, negative_pair_count=10, report_json="{}")'
)

content = content.replace(
    'db.activate_calibration("model_1", "ref_hash2", 0.8, 0.7, 0.1, 10, 10, "{}")',
    'db.activate_calibration(model_identity="model_1", reference_set_hash="ref_hash2", accept_threshold=0.8, review_threshold=0.7, minimum_margin=0.1, individual_strong_support_threshold=0.75, positive_pair_count=10, negative_pair_count=10, report_json="{}")'
)

with open(path, 'w', encoding='utf-8') as out:
    out.write(content)
