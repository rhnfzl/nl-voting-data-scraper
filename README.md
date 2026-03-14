<div align="center">

# nl-voting-data-scraper

[![PyPI](https://img.shields.io/pypi/v/nl-voting-data-scraper.svg)](https://pypi.org/project/nl-voting-data-scraper/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/nl-voting-data-scraper)](https://pypistats.org/packages/nl-voting-data-scraper)
[![Python package](https://github.com/rhnfzl/nl-voting-data-scraper/actions/workflows/publish.yml/badge.svg)](https://github.com/rhnfzl/nl-voting-data-scraper/actions/workflows/publish.yml)
[![Python Versions](https://img.shields.io/badge/Python-3.11%20|%203.12%20|%203.13-blue)](https://pypi.org/project/nl-voting-data-scraper/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Scrape Dutch voting advice ([StemWijzer](https://stemwijzer.nl)) data for any election: municipal, national, European, or provincial.
</div>

Outputs structured JSON with party positions, policy statements, and metadata. Reusable across election cycles.

### Key Features

- **Hybrid scraping**: API-first (fast HTTP) with Playwright browser automation fallback
- **Election-agnostic**: Municipal, national (Tweede Kamer), European Parliament, and provincial elections
- **CLI + Library**: Use from the command line or import in Python
- **Caching & resume**: File-based cache for interrupted batch scrapes (258+ municipalities)
- **Rate limiting**: Token-bucket rate limiter with exponential backoff
- **Base64/AES decoding**: Handles encoded StemWijzer API responses automatically
- **Structured output**: JSON format compatible with downstream vote guide applications

## Installation

```bash
pip install nl-voting-data-scraper
```

For browser automation fallback (optional):

```bash
pip install "nl-voting-data-scraper[browser]"
playwright install chromium
```

## Quick Start

### CLI

```bash
# List known elections
nl-voting-data-scraper list-elections

# Scrape all municipalities for 2026 municipal elections
nl-voting-data-scraper scrape gr2026 -o ./output

# Scrape a specific municipality
nl-voting-data-scraper scrape gr2026 -m GM0014 -o ./output

# Scrape national election
nl-voting-data-scraper scrape tk2025 -o ./output

# List municipalities for an election
nl-voting-data-scraper list-municipalities gr2026

# Discover API endpoints
nl-voting-data-scraper discover gr2026
```

### Python Library

```python
import asyncio
from nl_voting_data_scraper import StemwijzerScraper

async def main():
    async with StemwijzerScraper("gr2026") as scraper:
        # Scrape a single municipality
        data = await scraper.scrape_one("GM0014")
        print(f"{data.votematch.name}: {len(data.parties)} parties, {len(data.statements)} statements")

        # Scrape all
        results = await scraper.scrape()
        print(f"Scraped {len(results)} entries")

asyncio.run(main())
```

## Supported Elections

| Slug | Type | Year | Description |
|------|------|------|-------------|
| `gr2026` | Municipal | 2026 | Gemeenteraadsverkiezingen 2026 |
| `tk2025` | National | 2025 | Tweede Kamerverkiezingen 2025 |
| `tk2023` | National | 2023 | Tweede Kamerverkiezingen 2023 |
| `eu2024` | European | 2024 | Europees Parlement 2024 |
| `ps2023` | Provincial | 2023 | Provinciale Staten 2023 |

New elections are auto-detected from URL patterns. You can also pass custom election slugs.

## How It Works

```
                        ┌─────────────────────┐
                        │   StemwijzerScraper  │
                        │    (orchestrator)    │
                        └─────────┬───────────┘
                                  │
                    ┌─────────────┴─────────────┐
                    ▼                           ▼
          ┌─────────────────┐         ┌─────────────────┐
          │   API Scraper   │         │ Browser Scraper  │
          │   (primary)     │         │   (fallback)     │
          └────────┬────────┘         └────────┬────────┘
                   │                           │
                   ▼                           ▼
          ┌─────────────────┐         ┌─────────────────┐
          │ HTTP fetch from  │         │ Playwright       │
          │ data endpoint    │         │ network intercept│
          │ + base64 decode  │         │ or DOM scraping  │
          └────────┬────────┘         └────────┬────────┘
                   │                           │
                   └─────────────┬─────────────┘
                                 ▼
                       ┌─────────────────┐
                       │  Structured JSON │
                       │  (per election)  │
                       └─────────────────┘
```

1. **API-first (fast):** Fetches data from StemWijzer data endpoints via HTTP. Handles base64-encoded responses and optional AES decryption.
2. **Browser fallback:** If the API fails, uses Playwright to load the frontend, intercept network requests, and capture the data. Falls back to DOM extraction as a last resort.

## Output Format

Each municipality/election produces a JSON file:

```json
{
  "parties": [
    {
      "id": 206919,
      "name": "Party Name",
      "fullName": "Full Party Name",
      "website": "https://...",
      "hasSeats": true,
      "statements": [
        { "id": 206987, "position": "agree", "explanation": "..." }
      ]
    }
  ],
  "statements": [
    {
      "id": 206987,
      "theme": "Housing",
      "title": "The municipality should build more affordable housing.",
      "index": 1
    }
  ],
  "shootoutStatements": [...],
  "votematch": {
    "id": 206918,
    "name": "Municipality Name",
    "context": "2026GR",
    "remote_id": "GM0014",
    "langcode": "nl"
  }
}
```

## CLI Options

```
nl-voting-data-scraper scrape ELECTION [OPTIONS]

Options:
  -m, --municipality TEXT   Specific GM codes (repeatable)
  -l, --language TEXT       Languages to scrape (default: nl)
  -o, --output TEXT         Output directory (default: ./output)
  --combined                Also write combined.json
  --rate-limit FLOAT        Requests per second (default: 2.0)
  --no-cache                Disable caching
  --resume                  Resume interrupted scrape
  --browser-only            Only use browser scraping
  --api-only                Only use API scraping
  -v, --verbose             Verbose output
```

## Development

```bash
git clone https://github.com/rhnfzl/nl-voting-data-scraper.git
cd nl-voting-data-scraper
pip install -e ".[dev,browser]"
playwright install chromium
pytest
```

## Acknowledgements

Inspired by [afvanwoudenberg/stemwijzer](https://github.com/afvanwoudenberg/stemwijzer).

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
