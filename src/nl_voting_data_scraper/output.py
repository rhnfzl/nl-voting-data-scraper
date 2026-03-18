"""Output formatting: write scraped data to files."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from nl_voting_data_scraper.models import ElectionData, ElectionIndexEntry

OutputLayout = Literal["legacy", "engine"]


def write_election_data(
    data: ElectionData,
    output_dir: Path,
    source: str | None = None,
) -> Path:
    """Write a single election dataset to a JSON file.

    Args:
        data: The election data to write.
        output_dir: Directory to write to (created if missing).
        source: Filename stem (default: votematch.remote_id).

    Returns:
        Path to the written file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = source or data.votematch.remote_id
    path = output_dir / f"{stem}.json"
    path.write_text(
        json.dumps(data.model_dump(by_alias=True), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def write_index(
    entries: list[ElectionIndexEntry],
    output_path: Path,
) -> Path:
    """Write the election index to a JSON file."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            [e.model_dump(by_alias=True) for e in entries],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return output_path


def write_all(
    results: list[ElectionData],
    output_dir: Path,
    write_combined: bool = False,
    *,
    layout: OutputLayout = "legacy",
    election_slug: str | None = None,
) -> dict[str, Path]:
    """Write all scraped data to the output directory.

    Creates:
    - output_dir/{source}.json for each entry
    - output_dir/index.json with metadata
    - Optionally output_dir/combined.json with all data

    Returns:
        Dict mapping source names to file paths.
    """
    if layout == "legacy":
        return _write_all_legacy(results, output_dir, write_combined=write_combined)

    if layout == "engine":
        if not election_slug:
            raise ValueError("election_slug is required when layout='engine'")
        return _write_all_engine(
            results,
            output_dir,
            election_slug=election_slug,
            write_combined=write_combined,
        )

    raise ValueError(f"Unknown output layout: {layout}")


def _write_all_legacy(
    results: list[ElectionData],
    output_dir: Path,
    *,
    write_combined: bool = False,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}

    # Build index from data
    index_entries = []
    for data in results:
        vm = data.votematch
        source = vm.remote_id
        if vm.langcode != "nl":
            source = f"{vm.remote_id}-{vm.langcode}"

        path = write_election_data(data, output_dir, source)
        paths[source] = path

        index_entries.append(
            ElectionIndexEntry(
                id=vm.id,
                name=vm.name,
                source=source,
                remoteId=vm.remote_id,
                language=vm.langcode,
                decrypt=True,
            )
        )

    # Write index
    index_path = output_dir / "index.json"
    write_index(index_entries, index_path)
    paths["index"] = index_path

    # Optionally write combined file
    if write_combined:
        combined_path = output_dir / "combined.json"
        combined_path.write_text(
            json.dumps(
                [d.model_dump(by_alias=True) for d in results],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        paths["combined"] = combined_path

    return paths


def _write_all_engine(
    results: list[ElectionData],
    output_dir: Path,
    *,
    election_slug: str,
    write_combined: bool = False,
) -> dict[str, Path]:
    target_dir = output_dir / election_slug
    raw_dir = target_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    paths: dict[str, Path] = {}
    index_entries: list[ElectionIndexEntry] = []

    for data in results:
        vm = data.votematch
        source = vm.remote_id
        if vm.langcode != "nl":
            source = f"{vm.remote_id}-{vm.langcode}"

        path = write_election_data(data, raw_dir, source)
        paths[source] = path
        index_entries.append(
            ElectionIndexEntry(
                id=vm.id,
                name=vm.name,
                source=source,
                remoteId=vm.remote_id,
                language=vm.langcode,
                decrypt=True,
            )
        )

    index_path = target_dir / "index.json"
    write_index(index_entries, index_path)
    paths["index"] = index_path

    manifest_path = target_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "layout": "engine",
                "layoutVersion": 1,
                "election": election_slug,
                "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
                "entryCount": len(index_entries),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    paths["manifest"] = manifest_path

    if write_combined:
        combined_path = target_dir / "combined.json"
        combined_path.write_text(
            json.dumps(
                [d.model_dump(by_alias=True) for d in results],
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        paths["combined"] = combined_path

    return paths
