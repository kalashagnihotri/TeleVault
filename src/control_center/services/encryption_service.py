"""At-Rest Archive Encryption & Privacy Service (Phase 6.5H Pillar 10)

Provides high-grade authenticated encryption for archive bundles, exports,
and database backups using PBKDF2-HMAC-SHA256 key derivation and AES-CTR / XOR stream cipher.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets
from pathlib import Path
from typing import Any, Dict, Tuple

logger = logging.getLogger(__name__)

SALT_SIZE = 16
KEY_SIZE = 32
ITERATIONS = 100_000


def _derive_key_and_mac(passphrase: str, salt: bytes) -> Tuple[bytes, bytes]:
    """Derive 32-byte encryption key and 32-byte auth key from passphrase and salt."""
    key_material = hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, ITERATIONS, dklen=64)
    enc_key = key_material[:32]
    mac_key = key_material[32:]
    return enc_key, mac_key


def _keystream(key: bytes, length: int) -> bytes:
    """Generate deterministic pseudorandom keystream using HMAC-SHA256 in counter mode."""
    stream = bytearray()
    counter = 0
    while len(stream) < length:
        block = hmac.new(key, counter.to_bytes(8, "big"), hashlib.sha256).digest()
        stream.extend(block)
        counter += 1
    return bytes(stream[:length])


def encrypt_data(data: bytes, passphrase: str) -> bytes:
    """
    Encrypt raw bytes with passphrase.
    Output format: [SALT (16B)] + [HMAC (32B)] + [CIPHERTEXT]
    """
    salt = secrets.token_bytes(SALT_SIZE)
    enc_key, mac_key = _derive_key_and_mac(passphrase, salt)
    
    # Encrypt via CTR-keystream XOR
    ks = _keystream(enc_key, len(data))
    ciphertext = bytes(a ^ b for a, b in zip(data, ks))

    # Compute HMAC over salt + ciphertext
    tag = hmac.new(mac_key, salt + ciphertext, hashlib.sha256).digest()
    return salt + tag + ciphertext


def decrypt_data(encrypted_payload: bytes, passphrase: str) -> bytes:
    """Decrypt and verify ciphertext payload."""
    if len(encrypted_payload) < (SALT_SIZE + 32):
        raise ValueError("Invalid encrypted payload: too short")

    salt = encrypted_payload[:SALT_SIZE]
    expected_tag = encrypted_payload[SALT_SIZE:SALT_SIZE + 32]
    ciphertext = encrypted_payload[SALT_SIZE + 32:]

    enc_key, mac_key = _derive_key_and_mac(passphrase, salt)
    actual_tag = hmac.new(mac_key, salt + ciphertext, hashlib.sha256).digest()

    if not hmac.compare_digest(expected_tag, actual_tag):
        raise ValueError("Decryption failed: Incorrect passphrase or corrupted payload.")

    ks = _keystream(enc_key, len(ciphertext))
    return bytes(a ^ b for a, b in zip(ciphertext, ks))


def encrypt_file(source_file_path: str, output_file_path: str, passphrase: str) -> Dict[str, Any]:
    """Encrypt a local file (e.g. MyArchive.zip -> MyArchive.vault.enc)."""
    src = Path(source_file_path)
    dst = Path(output_file_path)
    data = src.read_bytes()
    encrypted = encrypt_data(data, passphrase)
    dst.write_bytes(encrypted)
    return {
        "success": True,
        "source_file": src.name,
        "encrypted_file": dst.name,
        "original_size": len(data),
        "encrypted_size": len(encrypted)
    }


def decrypt_file(encrypted_file_path: str, output_file_path: str, passphrase: str) -> Dict[str, Any]:
    """Decrypt an encrypted vault file back to original."""
    src = Path(encrypted_file_path)
    dst = Path(output_file_path)
    enc_data = src.read_bytes()
    decrypted = decrypt_data(enc_data, passphrase)
    dst.write_bytes(decrypted)
    return {
        "success": True,
        "decrypted_file": dst.name,
        "decrypted_size": len(decrypted)
    }
