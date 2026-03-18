"""Helpers for extracting historical StemWijzer payloads from app bundles.

This module keeps parsing policy separate from Playwright capture mechanics.
It supports two fallback paths:

1. Runtime capture by monkey-patching ``JSON.parse`` before the app boots.
2. Static extraction from captured JavaScript bundles.
"""

from __future__ import annotations

import ast
import base64
import json
import logging
import re
import urllib.parse
from collections.abc import Iterable
from copy import deepcopy
from typing import Any, TypeGuard, overload

from nl_voting_data_scraper.config import ElectionConfig
from nl_voting_data_scraper.models import ElectionIndexEntry

logger = logging.getLogger(__name__)

ContestPayload = dict[str, Any]

RUNTIME_CAPTURE_INIT_SCRIPT = """
(() => {
  if (globalThis.__stemwijzerCaptureInstalled) {
    return;
  }

  globalThis.__stemwijzerCaptureInstalled = true;
  globalThis.__stemwijzerParsedPayloads = [];
  const seen = new Set();
  const originalParse = JSON.parse;

  const remember = (candidate) => {
    try {
      if (!candidate || typeof candidate !== "object") return;
      if (!Array.isArray(candidate.parties) || !Array.isArray(candidate.statements)) return;
      const serialized = JSON.stringify(candidate);
      if (seen.has(serialized)) return;
      seen.add(serialized);
      globalThis.__stemwijzerParsedPayloads.push(serialized);
    } catch (error) {
      // Ignore parse-capture failures and let the page continue booting.
    }
  };

  JSON.parse = function patchedJsonParse(value, ...rest) {
    const parsed = originalParse.call(this, value, ...rest);
    remember(parsed);
    return parsed;
  };
})();
"""

BROWSER_STATE_CAPTURE_SCRIPT = """
() => {
  const clone = (value) => {
    try {
      return JSON.parse(JSON.stringify(value));
    } catch (error) {
      return null;
    }
  };

  const g = globalThis;
  const hasLegacyArrays =
    Array.isArray(g.objectNames) &&
    Array.isArray(g.propertyNames) &&
    Array.isArray(g.objectPropertyValues);

  return {
    locationHref: location.href,
    config: g.config && typeof g.config === "object" ? clone(g.config) : null,
    legacy: hasLegacyArrays
      ? {
          appID: typeof g.appID === "number" ? g.appID : 0,
          swName: typeof g.swName === "string" ? g.swName : "",
          objectNames: clone(g.objectNames) || [],
          objectIDs: clone(g.objectIDs) || [],
          objectImages: clone(g.objectImages) || [],
          objectSites: clone(g.objectSites) || [],
          objectPropertyValues: clone(g.objectPropertyValues) || [],
          objectPropertyMotivations: clone(g.objectPropertyMotivations) || [],
          objectPropertyLinks: clone(g.objectPropertyLinks) || [],
          propertyNames: clone(g.propertyNames) || [],
          propertyIDs: clone(g.propertyIDs) || [],
          propertyGroups: clone(g.propertyGroups) || [],
          propertyToGroupMapping: clone(g.propertyToGroupMapping) || [],
          propertyIntroductions: clone(g.propertyIntroductions) || [],
          themeClasses: clone(g.themaClasses) || {}
        }
      : null
  };
}
"""


def extract_contests_from_runtime_capture(
    payloads: Iterable[str | ContestPayload],
) -> list[ContestPayload]:
    """Parse captured runtime payloads into raw contest objects."""
    contests: list[ContestPayload] = []
    seen: set[str] = set()

    for payload in payloads:
        parsed: Any
        if isinstance(payload, str):
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                continue
        else:
            parsed = payload

        if not _is_contest_payload(parsed):
            continue

        key = _serialize_payload(parsed)
        if key in seen:
            continue
        seen.add(key)
        contests.append(parsed)

    return contests


def extract_contests_from_js_bundles(js_bundles: Iterable[str]) -> list[ContestPayload]:
    """Extract contest payloads from captured JavaScript bundle text."""
    patterns = (
        re.compile(
            r"JSON\.parse\(\s*decodeURIComponent\(\s*escape\(\s*atob\(\s*(?P<literal>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')\s*\)\s*\)\s*\)\s*\)",
            re.DOTALL,
        ),
        re.compile(
            r"JSON\.parse\(\s*decodeURIComponent\(\s*(?P<literal>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')\s*\)\s*\)",
            re.DOTALL,
        ),
        re.compile(
            r"JSON\.parse\(\s*atob\(\s*(?P<literal>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')\s*\)\s*\)",
            re.DOTALL,
        ),
        re.compile(
            r"JSON\.parse\(\s*(?P<literal>\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*')\s*\)",
            re.DOTALL,
        ),
    )

    contests: list[ContestPayload] = []
    seen: set[str] = set()

    for bundle in js_bundles:
        for pattern in patterns:
            for match in pattern.finditer(bundle):
                literal = match.group("literal")
                decoded_literal = _decode_js_literal(literal)
                if decoded_literal is None:
                    continue

                parsed = _parse_embedded_payload_string(decoded_literal)
                if not _is_contest_payload(parsed):
                    continue

                key = _serialize_payload(parsed)
                if key in seen:
                    continue
                seen.add(key)
                contests.append(parsed)

    return contests


def extract_contests_from_browser_state(
    snapshot: dict[str, Any] | None,
    config: ElectionConfig,
) -> list[ContestPayload]:
    """Extract normalized contest payloads from page globals captured in the browser."""
    if not isinstance(snapshot, dict):
        return []

    contests: list[ContestPayload] = []
    seen: set[str] = set()
    location_href = str(snapshot.get("locationHref") or config.app_url)

    for candidate in (
        _extract_contest_from_config_state(snapshot.get("config"), config, location_href),
        _extract_contest_from_legacy_state(snapshot.get("legacy"), config, location_href),
    ):
        if not _is_contest_payload(candidate):
            continue
        key = _serialize_payload(candidate)
        if key in seen:
            continue
        seen.add(key)
        contests.append(candidate)

    return contests


def normalize_contest_payload(
    payload: ContestPayload,
    config: ElectionConfig,
    *,
    source: str | None = None,
) -> ContestPayload:
    """Ensure a captured payload matches the canonical raw ElectionData shape."""
    normalized = deepcopy(payload)
    normalized.setdefault("shootoutStatements", [])

    votematch = deepcopy(normalized.get("votematch") or {})
    language = str(votematch.get("langcode") or _infer_language(source) or "nl").lower()
    source_name = build_source_name(config, source=source, language=language)
    remote_id = _derive_remote_id(source_name, language)

    votematch["id"] = int(votematch.get("id") or 0)
    votematch["name"] = str(votematch.get("name") or default_votematch_name(config))
    votematch["context"] = str(votematch.get("context") or config.context)
    votematch["date"] = str(votematch.get("date") or "")
    votematch["remote_id"] = str(votematch.get("remote_id") or remote_id)
    votematch["langcode"] = language
    normalized["votematch"] = votematch

    return normalized


def build_source_name(
    config: ElectionConfig,
    *,
    source: str | None = None,
    language: str = "nl",
) -> str:
    """Build a stable source name for a captured contest payload."""
    base = source or config.slug
    if language != "nl" and not base.endswith(f"-{language}"):
        return f"{base}-{language}"
    return base


def build_single_contest_index_entry(
    config: ElectionConfig,
    payload: ContestPayload,
    *,
    source: str | None = None,
) -> ElectionIndexEntry:
    """Create a synthetic index entry for a single-contest election."""
    if config.has_municipalities:
        raise ValueError(
            "Cannot synthesize a single-contest index for "
            f"multi-jurisdiction election {config.slug}"
        )

    normalized = normalize_contest_payload(payload, config, source=source)
    votematch = normalized["votematch"]
    source_name = build_source_name(
        config,
        source=source or votematch["remote_id"],
        language=votematch["langcode"],
    )

    return ElectionIndexEntry(
        id=votematch["id"],
        name=votematch["name"],
        source=source_name,
        remoteId=votematch["remote_id"],
        language=votematch["langcode"],
        decrypt=True,
    )


def default_votematch_name(config: ElectionConfig) -> str:
    """Return a human-readable default title for a known election slug."""
    labels = {
        "gr2026": "Gemeenteraadsverkiezingen 2026",
        "tk2025": "Tweede Kamerverkiezing 2025",
        "tk2023": "Tweede Kamerverkiezing 2023",
        "tk2021": "Tweede Kamerverkiezing 2021",
        "tk2017": "Tweede Kamerverkiezing 2017",
        "tk2012": "Tweede Kamerverkiezing 2012",
        "tk2010": "Tweede Kamerverkiezing 2010",
        "tk2006": "Tweede Kamerverkiezing 2006",
        "eu2024": "Europese verkiezing 2024",
        "ps2023": "Provinciale Statenverkiezing 2023",
    }
    return labels.get(config.slug, config.description.split(" (", 1)[0] or config.slug)


def _extract_contest_from_config_state(
    payload: Any,
    config: ElectionConfig,
    location_href: str,
) -> ContestPayload | None:
    if not isinstance(payload, dict):
        return None

    parties_payload = payload.get("parties")
    statements_payload = payload.get("statements")
    if not isinstance(parties_payload, list) or not isinstance(statements_payload, list):
        return None

    themes_payload = payload.get("themes")
    theme_by_statement: dict[int, dict[str, Any]] = {}
    if isinstance(themes_payload, list):
        for item in themes_payload:
            if not isinstance(item, dict):
                continue
            statement_id = _coerce_int(item.get("statementID"))
            if statement_id is None:
                continue
            theme_by_statement[statement_id] = item

    statements: list[dict[str, Any]] = []
    for index, item in enumerate(statements_payload, start=1):
        if not isinstance(item, dict):
            continue
        statement_id = _coerce_int(item.get("statementID"), default=index)
        theme_entry = theme_by_statement.get(statement_id, {})
        statement: dict[str, Any] = {
            "id": statement_id,
            "index": index,
            "theme": str(theme_entry.get("theme") or ""),
            "themeId": str(theme_entry.get("themeID") or f"statement-{statement_id}"),
            "title": str(item.get("statement") or "").strip(),
        }
        explanation = _flatten_text(item.get("explanation"))
        if explanation:
            statement["moreInfo"] = {"text": explanation}
        statements.append(statement)

    parties: list[dict[str, Any]] = []
    for index, item in enumerate(parties_payload, start=1):
        if not isinstance(item, dict):
            continue
        positions: list[dict[str, Any]] = []
        for raw_position in item.get("statements") or []:
            if not isinstance(raw_position, dict):
                continue
            statement_id = _coerce_int(raw_position.get("statementID"))
            if statement_id is None:
                continue
            position: dict[str, Any] = {
                "id": statement_id,
                "position": _map_position(raw_position.get("position")),
            }
            explanation = _flatten_text(raw_position.get("explanation"))
            if explanation:
                position["explanation"] = explanation
            positions.append(position)

        name = str(item.get("short") or item.get("name") or f"Party {index}")
        parties.append(
            {
                "id": _coerce_int(item.get("partyID"), default=index),
                "name": name,
                "fullName": str(item.get("name") or name),
                "logo": _resolve_relative_url(location_href, item.get("logo")),
                "website": str(item.get("link") or ""),
                "participates": bool(item.get("activated", True)),
                "statements": positions,
            }
        )

    return {
        "parties": parties,
        "statements": statements,
        "shootoutStatements": [],
        "votematch": {
            "id": _coerce_int(payload.get("votematchID"), default=0),
            "name": str(payload.get("name") or default_votematch_name(config)),
            "context": config.context,
            "date": "",
            "remote_id": config.slug,
            "langcode": str(payload.get("lang") or "nl"),
        },
    }


def _extract_contest_from_legacy_state(
    payload: Any,
    config: ElectionConfig,
    location_href: str,
) -> ContestPayload | None:
    if not isinstance(payload, dict):
        return None

    object_names = payload.get("objectNames")
    property_names = payload.get("propertyNames")
    object_property_values = payload.get("objectPropertyValues")
    if (
        not isinstance(object_names, list)
        or not isinstance(property_names, list)
        or not isinstance(object_property_values, list)
    ):
        return None

    object_ids = _as_list(payload.get("objectIDs"))
    object_images = _as_list(payload.get("objectImages"))
    object_sites = _as_list(payload.get("objectSites"))
    object_motivations = _as_list(payload.get("objectPropertyMotivations"))
    property_ids = _as_list(payload.get("propertyIDs"))
    property_groups = _as_list(payload.get("propertyGroups"))
    property_mapping = _as_list(payload.get("propertyToGroupMapping"))
    property_introductions = _as_list(payload.get("propertyIntroductions"))
    theme_classes = _as_dict(payload.get("themeClasses"))

    statements: list[dict[str, Any]] = []
    statement_ids: list[int] = []
    for index, raw_title in enumerate(property_names, start=1):
        statement_id = _coerce_int(
            property_ids[index - 1] if index - 1 < len(property_ids) else None,
            default=index,
        )
        statement_ids.append(statement_id)
        theme = _derive_legacy_theme(
            statement_id=statement_id,
            property_index=index - 1,
            property_groups=property_groups,
            property_mapping=property_mapping,
            theme_classes=theme_classes,
        )
        statement: dict[str, Any] = {
            "id": statement_id,
            "index": index,
            "theme": theme,
            "themeId": _slugify(theme) or f"statement-{statement_id}",
            "title": str(raw_title or "").strip(),
        }
        intro = _clean_text(
            property_introductions[index - 1] if index - 1 < len(property_introductions) else None
        )
        if intro:
            statement["moreInfo"] = {"text": intro}
        statements.append(statement)

    parties: list[dict[str, Any]] = []
    for index, raw_name in enumerate(object_names, start=1):
        row = object_property_values[index - 1] if index - 1 < len(object_property_values) else []
        if not isinstance(row, list):
            continue

        positions: list[dict[str, Any]] = []
        motivation_row = (
            object_motivations[index - 1]
            if index - 1 < len(object_motivations)
            and isinstance(object_motivations[index - 1], list)
            else []
        )
        for property_index, raw_value in enumerate(row):
            if property_index >= len(statement_ids):
                continue
            position: dict[str, Any] = {
                "id": statement_ids[property_index],
                "position": _map_position(raw_value),
            }
            explanation = _clean_text(
                motivation_row[property_index] if property_index < len(motivation_row) else None
            )
            if explanation:
                position["explanation"] = explanation
            positions.append(position)

        party_id = _coerce_int(
            object_ids[index - 1] if index - 1 < len(object_ids) else None,
            default=index,
        )
        name = str(raw_name or f"Party {index}")
        parties.append(
            {
                "id": party_id,
                "name": name,
                "fullName": name,
                "logo": _resolve_relative_url(
                    location_href,
                    object_images[index - 1] if index - 1 < len(object_images) else None,
                ),
                "website": _clean_text(
                    object_sites[index - 1] if index - 1 < len(object_sites) else None
                ),
                "participates": True,
                "statements": positions,
            }
        )

    return {
        "parties": parties,
        "statements": statements,
        "shootoutStatements": [],
        "votematch": {
            "id": _coerce_int(payload.get("appID"), default=0),
            "name": _decode_percent_text(_clean_text(payload.get("swName")))
            or default_votematch_name(config),
            "context": config.context,
            "date": "",
            "remote_id": config.slug,
            "langcode": "nl",
        },
    }


def _decode_js_literal(literal: str) -> str | None:
    try:
        value = ast.literal_eval(literal)
    except (SyntaxError, ValueError):
        return None
    return value if isinstance(value, str) else None


def _parse_embedded_payload_string(candidate: str) -> ContestPayload | None:
    texts: list[str] = [candidate]

    unquoted = urllib.parse.unquote(candidate)
    if unquoted != candidate:
        texts.append(unquoted)

    if _looks_like_base64(candidate):
        decoded = _decode_base64_text(candidate)
        if decoded is not None:
            texts.append(decoded)
            decoded_unquoted = urllib.parse.unquote(decoded)
            if decoded_unquoted != decoded:
                texts.append(decoded_unquoted)

    for text in texts:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue

        if _is_contest_payload(parsed):
            return parsed

    return None


def _looks_like_base64(value: str) -> bool:
    compact = value.strip()
    return len(compact) >= 32 and re.fullmatch(r"[A-Za-z0-9+/=_-]+", compact) is not None


def _decode_base64_text(value: str) -> str | None:
    compact = value.strip()
    padding = "=" * ((4 - len(compact) % 4) % 4)
    try:
        decoded = base64.b64decode(compact + padding)
    except Exception:
        return None
    return decoded.decode("utf-8", errors="ignore")


def _infer_language(source: str | None) -> str | None:
    if not source or "-" not in source:
        return None
    maybe_language = source.rsplit("-", 1)[-1]
    if len(maybe_language) == 2 and maybe_language.isalpha():
        return maybe_language
    return None


def _derive_remote_id(source: str, language: str) -> str:
    if language != "nl" and source.endswith(f"-{language}"):
        return source[: -(len(language) + 1)]
    return source


def _is_contest_payload(payload: Any) -> TypeGuard[ContestPayload]:
    return (
        isinstance(payload, dict)
        and isinstance(payload.get("parties"), list)
        and isinstance(payload.get("statements"), list)
    )


def _serialize_payload(payload: ContestPayload) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


@overload
def _coerce_int(value: Any, *, default: int) -> int: ...


@overload
def _coerce_int(value: Any, *, default: None = None) -> int | None: ...


def _coerce_int(value: Any, *, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_dict(value: Any) -> dict[Any, Any]:
    return value if isinstance(value, dict) else {}


def _clean_text(value: Any) -> str:
    if value in (None, "", "null", False):
        return ""
    return str(value).strip()


def _flatten_text(value: Any) -> str:
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, dict):
                parts.append(_clean_text(item.get("text")))
            else:
                parts.append(_clean_text(item))
        return " ".join(part for part in parts if part).strip()
    return _clean_text(value)


def _map_position(value: Any) -> str:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = 0
    if numeric > 0:
        return "agree"
    if numeric < 0:
        return "disagree"
    return "neither"


def _resolve_relative_url(base_url: str, value: Any) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    return urllib.parse.urljoin(base_url, text)


def _derive_legacy_theme(
    *,
    statement_id: int,
    property_index: int,
    property_groups: list[Any],
    property_mapping: list[Any],
    theme_classes: dict[Any, Any],
) -> str:
    if property_index < len(property_mapping):
        try:
            group_index = int(property_mapping[property_index])
        except (TypeError, ValueError):
            group_index = -1
        if 0 <= group_index < len(property_groups):
            return _clean_text(property_groups[group_index])

    theme_key = f"ID{statement_id}"
    theme = _clean_text(theme_classes.get(theme_key))
    return theme or "Overig"


def _slugify(value: str) -> str:
    return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", value.lower()))


def _decode_percent_text(value: str) -> str:
    if "%" not in value:
        return value
    return urllib.parse.unquote(value)
