"""Shared test fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_municipality() -> dict:
    """Sample municipality raw data."""
    return json.loads((FIXTURES_DIR / "sample_municipality.json").read_text())


@pytest.fixture
def sample_index() -> list[dict]:
    """Sample election index data."""
    return json.loads((FIXTURES_DIR / "sample_index.json").read_text())


@pytest.fixture
def tmp_cache(tmp_path) -> Path:
    """Temporary cache directory."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    return cache_dir
