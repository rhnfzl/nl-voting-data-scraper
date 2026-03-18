"""Tests for output writers."""

from __future__ import annotations

import json
from pathlib import Path

from nl_voting_data_scraper.models import ElectionData
from nl_voting_data_scraper.output import write_all

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def load_sample_data() -> ElectionData:
    payload = json.loads((FIXTURE_DIR / "sample_municipality.json").read_text(encoding="utf-8"))
    return ElectionData.model_validate(payload)


def test_write_all_preserves_legacy_layout(tmp_path: Path):
    paths = write_all([load_sample_data()], tmp_path, write_combined=True)

    assert (tmp_path / "GM0415.json").exists()
    assert (tmp_path / "index.json").exists()
    assert (tmp_path / "combined.json").exists()
    assert paths["GM0415"] == tmp_path / "GM0415.json"


def test_write_all_supports_engine_layout(tmp_path: Path):
    paths = write_all(
        [load_sample_data()],
        tmp_path,
        layout="engine",
        election_slug="gr2026",
        write_combined=True,
    )

    target_dir = tmp_path / "gr2026"
    assert (target_dir / "raw" / "GM0415.json").exists()
    assert (target_dir / "index.json").exists()
    assert (target_dir / "manifest.json").exists()
    assert (target_dir / "combined.json").exists()
    assert paths["GM0415"] == target_dir / "raw" / "GM0415.json"

    manifest = json.loads((target_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["layout"] == "engine"
    assert manifest["election"] == "gr2026"
    assert manifest["entryCount"] == 1
