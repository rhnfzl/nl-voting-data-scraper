"""Tests for response decoder."""

import base64
import json

import pytest

from nl_voting_data_scraper.decoder import DecodeError, decode_response, extract_key_from_js


class TestDecodeResponse:
    def test_plain_json(self):
        data = {"hello": "world"}
        result = decode_response(json.dumps(data))
        assert result == data

    def test_plain_json_list(self):
        data = [{"id": 1}, {"id": 2}]
        result = decode_response(json.dumps(data))
        assert result == data

    def test_base64_json(self):
        data = {"parties": [], "statements": []}
        encoded = base64.b64encode(json.dumps(data).encode()).decode()
        result = decode_response(encoded)
        assert result == data

    def test_base64_json_list(self):
        data = [{"id": 1, "name": "test"}]
        encoded = base64.b64encode(json.dumps(data).encode()).decode()
        result = decode_response(encoded)
        assert result == data

    def test_bytes_input(self):
        data = {"key": "value"}
        result = decode_response(json.dumps(data).encode())
        assert result == data

    def test_invalid_data_raises(self):
        with pytest.raises(DecodeError):
            decode_response("not valid json or base64!!!")

    def test_whitespace_stripped(self):
        data = {"test": True}
        result = decode_response(f"  {json.dumps(data)}  ")
        assert result == data


class TestExtractKeyFromJs:
    def test_extract_decrypt_key(self):
        js = 'var data = CryptoJS.AES.decrypt(payload, "my_secret_key_123");'
        key = extract_key_from_js(js)
        assert key == "my_secret_key_123"

    def test_extract_secret_key(self):
        js = 'const SECRET_KEY = "another_key_456";'
        key = extract_key_from_js(js)
        assert key == "another_key_456"

    def test_no_key_found(self):
        js = "console.log('hello world');"
        key = extract_key_from_js(js)
        assert key is None

    def test_extract_decrypt_function(self):
        js = 'function load(d) { return decrypt(d, "key789"); }'
        key = extract_key_from_js(js)
        assert key == "key789"
