"""Decode and decrypt StemWijzer API responses.

StemWijzer data endpoints use multiple encoding layers:
- Plain JSON (index.json)
- JSON string > base64 > URL-encoded JSON (municipality data with decrypt=true)
- Base64 > JSON (older format)
- Base64 > AES decrypt > JSON (if encryption key provided)
"""

from __future__ import annotations

import base64
import json
import re
import urllib.parse
from typing import cast

from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad


class DecodeError(Exception):
    """Failed to decode a StemWijzer response."""


def decode_response(data: str | bytes, decrypt_key: str | None = None) -> dict | list:
    """Decode a StemWijzer API response.

    Tries strategies in order:
    1. Plain JSON (dict or list)
    2. JSON string > base64 > URL-decode > JSON (decrypt=true format)
    3. Base64 > JSON
    4. Base64 > AES decrypt > JSON (if key provided)

    Returns parsed JSON (dict or list).
    """
    if isinstance(data, bytes):
        data = data.decode("utf-8", errors="replace")

    data = data.strip()

    # Strategy 1: plain JSON (dict or list)
    try:
        parsed = json.loads(data)
        if isinstance(parsed, (dict, list)):
            return parsed
        # If parsed is a string, it's likely base64-encoded content (strategy 2)
        if isinstance(parsed, str):
            return _decode_b64_urlencoded(parsed)
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: raw base64 > URL-decode > JSON
    try:
        return _decode_b64_urlencoded(data)
    except Exception:
        pass

    # Strategy 3: base64 > JSON (without URL encoding)
    try:
        decoded = base64.b64decode(data)
        return cast(dict | list, json.loads(decoded))
    except Exception:
        pass

    # Strategy 4: base64 > AES decrypt > JSON
    if decrypt_key:
        try:
            return _aes_decrypt(data, decrypt_key)
        except Exception:
            pass

    raise DecodeError(f"Failed to decode response (length={len(data)}, starts={data[:80]!r})")


def _decode_b64_urlencoded(data: str) -> dict | list:
    """Decode base64 > URL-decode > JSON.

    StemWijzer municipality data (decrypt=true) uses this encoding:
    base64 string > URL-encoded JSON > actual JSON.
    """
    # Add padding if needed
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding

    decoded_bytes = base64.b64decode(data)
    url_encoded = decoded_bytes.decode("utf-8")
    json_str = urllib.parse.unquote(url_encoded)
    return cast(dict | list, json.loads(json_str))


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
    return cast(dict | list, json.loads(plaintext))


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
