import pytest
import hashlib
from pathlib import Path
from src.hashing import sha256_file, get_reference_set_hash

def test_sha256_file(tmp_path: Path):
    test_file = tmp_path / "test.txt"
    test_file.write_bytes(b"hello world")
    
    expected = hashlib.sha256(b"hello world").hexdigest()
    assert sha256_file(test_file) == expected
    
def test_reference_set_hash_compatibility():
    hashes = [
        "b" * 64,
        "a" * 64,
    ]

    expected = hashlib.sha256(
        (("a" * 64) + ("b" * 64)).encode("utf-8")
    ).hexdigest()

    assert get_reference_set_hash(hashes) == expected

def test_reference_set_hash_empty():
    assert get_reference_set_hash([]) == "empty"
    assert get_reference_set_hash([None, "", "   "]) == "empty"
