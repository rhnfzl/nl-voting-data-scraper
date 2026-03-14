"""Election configurations and URL patterns."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ElectionConfig:
    """Configuration for a specific election."""

    slug: str
    election_type: str  # "municipal", "national", "european", "provincial"
    year: int
    app_url: str
    data_url: str
    context: str  # e.g. "2026GR", "2025TK"
    has_municipalities: bool = False
    description: str = ""


KNOWN_ELECTIONS: dict[str, ElectionConfig] = {
    "gr2026": ElectionConfig(
        slug="gr2026",
        election_type="municipal",
        year=2026,
        app_url="https://gemeenteraad2026.stemwijzer.nl",
        data_url="https://gr2026-data.stemwijzer.nl",
        context="2026GR",
        has_municipalities=True,
        description="Gemeenteraadsverkiezingen 2026 (Municipal elections 2026)",
    ),
    "tk2025": ElectionConfig(
        slug="tk2025",
        election_type="national",
        year=2025,
        app_url="https://tweedekamer2025.stemwijzer.nl",
        data_url="https://tk2025-data.stemwijzer.nl",
        context="2025TK",
        has_municipalities=False,
        description="Tweede Kamerverkiezingen 2025 (Parliamentary elections 2025)",
    ),
    "tk2023": ElectionConfig(
        slug="tk2023",
        election_type="national",
        year=2023,
        app_url="https://tweedekamer2023.stemwijzer.nl",
        data_url="https://tk2023-data.stemwijzer.nl",
        context="2023TK",
        has_municipalities=False,
        description="Tweede Kamerverkiezingen 2023 (Parliamentary elections 2023)",
    ),
    "eu2024": ElectionConfig(
        slug="eu2024",
        election_type="european",
        year=2024,
        app_url="https://eu.stemwijzer.nl",
        data_url="https://eu2024-data.stemwijzer.nl",
        context="2024EP",
        has_municipalities=False,
        description="Europees Parlement 2024 (European Parliament elections 2024)",
    ),
    "ps2023": ElectionConfig(
        slug="ps2023",
        election_type="provincial",
        year=2023,
        app_url="https://provinciaalestaten2023.stemwijzer.nl",
        data_url="https://ps2023-data.stemwijzer.nl",
        context="2023PS",
        has_municipalities=True,  # provinces
        description="Provinciale Statenverkiezingen 2023 (Provincial elections 2023)",
    ),
}


# URL patterns to try when probing for data endpoints
DATA_URL_PATTERNS = [
    "https://{slug}-data.stemwijzer.nl",
    "https://data.stemwijzer.nl/{slug}",
    "https://{slug}.stemwijzer.nl/data",
]

# Default HTTP headers for API requests
DEFAULT_HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "nl-NL,nl;q=0.9,en-US;q=0.8,en;q=0.7",
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    ),
}


def get_election_config(slug: str) -> ElectionConfig | None:
    """Get election config by slug."""
    return KNOWN_ELECTIONS.get(slug)


def build_custom_election(
    slug: str,
    election_type: str = "municipal",
    year: int = 2026,
    app_url: str | None = None,
    data_url: str | None = None,
) -> ElectionConfig:
    """Build a custom election config from a slug."""
    return ElectionConfig(
        slug=slug,
        election_type=election_type,
        year=year,
        app_url=app_url or f"https://{slug}.stemwijzer.nl",
        data_url=data_url or f"https://{slug}-data.stemwijzer.nl",
        context=f"{year}{slug.upper()[:2]}",
        has_municipalities=election_type in ("municipal", "provincial"),
    )
