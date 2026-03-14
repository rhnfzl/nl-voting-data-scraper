"""File-based cache with resume support for interrupted scrapes."""

from __future__ import annotations

import json
from pathlib import Path

from nl_voting_data_scraper.models import ElectionData


class ScrapeCache:
    """Persistent file-based cache for scraped election data."""

    def __init__(self, cache_dir: Path | str):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _key_path(self, election: str, source: str) -> Path:
        election_dir = self.cache_dir / election
        election_dir.mkdir(parents=True, exist_ok=True)
        return election_dir / f"{source}.json"

    def has(self, election: str, source: str) -> bool:
        """Check if a cached result exists."""
        return self._key_path(election, source).exists()

    def get(self, election: str, source: str) -> ElectionData | None:
        """Get cached result, or None."""
        path = self._key_path(election, source)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return ElectionData.model_validate(data)

    def get_raw(self, election: str, source: str) -> dict | None:
        """Get cached result as raw dict."""
        path = self._key_path(election, source)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def put(self, election: str, source: str, data: dict | ElectionData) -> None:
        """Cache a result."""
        path = self._key_path(election, source)
        if isinstance(data, ElectionData):
            json_data = data.model_dump(by_alias=True)
        else:
            json_data = data
        path.write_text(json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8")

    def put_raw(self, election: str, source: str, data: str | bytes) -> None:
        """Cache raw response data (before decoding)."""
        path = self._key_path(election, source)
        path = path.with_suffix(".raw")
        if isinstance(data, bytes):
            path.write_bytes(data)
        else:
            path.write_text(data, encoding="utf-8")

    def list_cached(self, election: str) -> list[str]:
        """List all cached sources for an election."""
        election_dir = self.cache_dir / election
        if not election_dir.exists():
            return []
        return [p.stem for p in election_dir.glob("*.json")]

    def clear(self, election: str | None = None) -> int:
        """Clear cache. Returns number of files removed."""
        import shutil

        count = 0
        if election:
            election_dir = self.cache_dir / election
            if election_dir.exists():
                count = len(list(election_dir.glob("*")))
                shutil.rmtree(election_dir)
        else:
            for d in self.cache_dir.iterdir():
                if d.is_dir():
                    count += len(list(d.glob("*")))
                    shutil.rmtree(d)
        return count
