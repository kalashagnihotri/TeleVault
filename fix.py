import sys

path = 'tests/test_prepare_lfw_negatives.py'
with open(path, 'r', encoding='utf-8') as f:
    c = f.read()

mock_report = "{'seed': 42, 'identities_available': 0, 'identities_examined': 0, 'identities_exhausted': 0, 'images_examined': 0, 'decode_errors': 0, 'zero_detections': 0, 'tiny_only': 0, 'multiple_accepted_faces': 0, 'duplicate_content': 0, 'alignment_errors': 0, 'embedding_errors': 0, 'accepted_calibration': 0, 'accepted_holdout': 0}"
c = c.replace('], {})', f'], {mock_report})')

with open(path, 'w', encoding='utf-8') as f:
    f.write(c)
