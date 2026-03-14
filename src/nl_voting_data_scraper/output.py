"""Output formatting: write scraped data to files."""

from __future__ import annotations

import json
from pathlib import Path

from nl_voting_data_scraper.models import ElectionData, ElectionIndexEntry


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
) -> dict[str, Path]:
    """Write all scraped data to the output directory.

    Creates:
    - output_dir/{source}.json for each entry
    - output_dir/index.json with metadata
    - Optionally output_dir/combined.json with all data

    Returns:
        Dict mapping source names to file paths.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {}

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
