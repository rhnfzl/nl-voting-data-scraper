"""Decode and decrypt StemWijzer API responses.

StemWijzer data endpoints return base64-encoded JSON. Some elections
additionally use AES encryption (indicated by decrypt=true in the index).
"""

from __future__ import annotations

import base64
import json
import re

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad


class DecodeError(Exception):
    """Failed to decode a StemWijzer response."""


def decode_response(data: str | bytes, decrypt_key: str | None = None) -> dict | list:
    """Decode a StemWijzer API response.

    Tries strategies in order:
    1. Plain JSON
    2. Base64 → JSON
    3. Base64 → AES decrypt → JSON (if key provided)

    Returns parsed JSON (dict or list).
    """
    if isinstance(data, bytes):
        data = data.decode("utf-8", errors="replace")

    data = data.strip()

    # Strategy 1: plain JSON
    try:
        return json.loads(data)
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: base64 → JSON
    try:
        decoded = base64.b64decode(data)
        return json.loads(decoded)
    except Exception:
        pass

    # Strategy 3: base64 → AES decrypt → JSON
    if decrypt_key:
        try:
            return _aes_decrypt(data, decrypt_key)
        except Exception:
            pass

    raise DecodeError(f"Failed to decode response (length={len(data)}, starts={data[:80]!r})")


def _aes_decrypt(data: str, key: str) -> dict | list:
    """Decrypt AES-CBC encrypted data.

    The StemWijzer format uses:
    - Base64 encoded ciphertext
    - First 16 bytes = IV
    - Key derived from the provided string (UTF-8, padded/truncated to 32 bytes)
    """
    raw = base64.b64decode(data)
    iv = raw[:16]
    ciphertext = raw[16:]

    # Derive 32-byte key from string
    key_bytes = key.encode("utf-8")
    key_bytes = key_bytes.ljust(32, b"\0")[:32]

    cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
    plaintext = unpad(cipher.decrypt(ciphertext), AES.block_size)
    return json.loads(plaintext)


def extract_key_from_js(js_source: str) -> str | None:
    """Try to extract the AES encryption key from a JS bundle.

    Searches for common patterns like:
    - CryptoJS.AES.decrypt(data, "key")
    - decrypt(data, "key")
    - key: "..."
    - SECRET_KEY = "..."
    """
    patterns = [
        r'decrypt\s*\([^,]+,\s*["\']([^"\']+)["\']',
        r'(?:secret|key|SECRET_KEY|DECRYPT_KEY)\s*[:=]\s*["\']([^"\']+)["\']',
        r'AES\.decrypt\s*\([^,]+,\s*["\']([^"\']+)["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, js_source)
        if match:
            return match.group(1)
    return None
