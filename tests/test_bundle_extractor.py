"""Tests for historical bundle extraction helpers."""

from __future__ import annotations

import json
from pathlib import Path

from nl_voting_data_scraper.bundle_extractor import (
    build_single_contest_index_entry,
    extract_contests_from_browser_state,
    extract_contests_from_js_bundles,
    extract_contests_from_runtime_capture,
    normalize_contest_payload,
)
from nl_voting_data_scraper.config import KNOWN_ELECTIONS

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_extracts_plain_json_parse_payload_from_tk2023_fixture():
    bundle = (FIXTURE_DIR / "tk2023_bundle.js").read_text(encoding="utf-8")
    contests = extract_contests_from_js_bundles([bundle])

    assert len(contests) == 1
    assert contests[0]["parties"][0]["name"] == "D66"
    assert contests[0]["statements"][0]["theme"] == "Wonen"


def test_extracts_base64_urlencoded_payload_from_eu2024_fixture():
    bundle = (FIXTURE_DIR / "eu2024_bundle.js").read_text(encoding="utf-8")
    contests = extract_contests_from_js_bundles([bundle])

    assert len(contests) == 1
    assert contests[0]["parties"][0]["name"] == "Volt"
    assert "klimaatbeleid" in contests[0]["statements"][0]["title"]


def test_runtime_capture_normalization_backfills_votematch_metadata():
    captured = [
        json.dumps(
            {
                "parties": [{"id": 1, "name": "D66", "statements": []}],
                "statements": [{"id": 101, "index": 1, "theme": "Wonen", "title": "Bouwen"}],
                "shootoutStatements": [],
            }
        )
    ]

    contests = extract_contests_from_runtime_capture(captured)
    normalized = normalize_contest_payload(contests[0], KNOWN_ELECTIONS["tk2023"])
    entry = build_single_contest_index_entry(KNOWN_ELECTIONS["tk2023"], contests[0])

    assert normalized["votematch"]["name"] == "Tweede Kamerverkiezing 2023"
    assert normalized["votematch"]["remote_id"] == "tk2023"
    assert normalized["votematch"]["langcode"] == "nl"
    assert entry.source == "tk2023"
    assert entry.remoteId == "tk2023"


def test_extracts_config_state_from_archived_tk2017_page_globals():
    snapshot = {
        "locationHref": "https://web.archive.org/web/20170206221248/http://tweedekamer2017.stemwijzer.nl/",
        "config": {
            "votematchID": 6948,
            "name": "StemWijzer Tweede Kamer 2017",
            "lang": "nl",
            "themes": [
                {
                    "themeID": "bindend-referendum",
                    "statementID": 6992,
                    "theme": "Bindend referendum",
                }
            ],
            "statements": [
                {
                    "statementID": 6992,
                    "statement": "Er moet een bindend referendum komen.",
                    "explanation": [],
                }
            ],
            "parties": [
                {
                    "partyID": 1078,
                    "name": "Volkspartij voor Vrijheid en Democratie",
                    "short": "VVD",
                    "link": "https://web.archive.org/web/20170207093139/http://vvd.nl",
                    "logo": "logos/vvd.svg",
                    "statements": [
                        {
                            "statementID": 6992,
                            "position": -1,
                            "explanation": "De VVD is tegen.",
                        }
                    ],
                }
            ],
        },
    }

    contests = extract_contests_from_browser_state(snapshot, KNOWN_ELECTIONS["tk2017"])

    assert len(contests) == 1
    assert contests[0]["votematch"]["name"] == "StemWijzer Tweede Kamer 2017"
    assert contests[0]["statements"][0]["theme"] == "Bindend referendum"
    assert contests[0]["parties"][0]["name"] == "VVD"
    assert contests[0]["parties"][0]["statements"][0]["position"] == "disagree"


def test_extracts_legacy_globals_from_archived_tk2012_page_globals():
    snapshot = {
        "locationHref": "https://web.archive.org/web/20120902015428/http://www.stemwijzer.nl/TK2012/index.html",
        "legacy": {
            "appID": 20218,
            "swName": "StemWijzer Tweede Kamer 2012",
            "objectNames": ["VVD"],
            "objectIDs": [20223],
            "objectImages": ["../logos/vvd.jpg"],
            "objectSites": ["http://example.com/vvd"],
            "objectPropertyValues": [[1, -1]],
            "objectPropertyMotivations": [["Voor", "Tegen"]],
            "objectPropertyLinks": [["", ""]],
            "propertyNames": [
                "Het tekort op de begroting mag in 2013 niet meer dan 3% bedragen.",
                "Het aantal leden van de Tweede Kamer moet 150 blijven.",
            ],
            "propertyIDs": [20340, 20341],
            "propertyGroups": ["Economie"],
            "propertyToGroupMapping": [0, 0],
            "propertyIntroductions": ["Meer context", "null"],
            "themeClasses": {},
        },
    }

    contests = extract_contests_from_browser_state(snapshot, KNOWN_ELECTIONS["tk2012"])

    assert len(contests) == 1
    assert contests[0]["votematch"]["id"] == 20218
    assert contests[0]["parties"][0]["name"] == "VVD"
    assert contests[0]["parties"][0]["statements"][0]["position"] == "agree"
    assert contests[0]["parties"][0]["statements"][1]["explanation"] == "Tegen"
    assert contests[0]["statements"][0]["theme"] == "Economie"
    assert contests[0]["statements"][0]["moreInfo"]["text"] == "Meer context"
