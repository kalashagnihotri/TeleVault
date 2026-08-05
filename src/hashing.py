from __future__ import annotations

import hashlib
from pathlib import Path

def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()

def get_calibration_scope_hash(model_identity: str, base_reference_set_hash: str, policy_identity: str) -> str:
    scope_material = (
        f"model={model_identity}\n"
        f"references={base_reference_set_hash}\n"
        f"policy={policy_identity}\n"
        f"calibration_schema=v2"
    )
    return hashlib.sha256(scope_material.encode("utf-8")).hexdigest()
