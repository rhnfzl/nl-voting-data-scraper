"""Tests for StemwijzerScraper orchestrator."""

from unittest.mock import AsyncMock, patch

import pytest

from nl_voting_data_scraper import KNOWN_ELECTIONS, ElectionConfig
from nl_voting_data_scraper.api_scraper import APIScraperError
from nl_voting_data_scraper.browser_scraper import InterceptedData
from nl_voting_data_scraper.models import ElectionIndexEntry
from nl_voting_data_scraper.scraper import StemwijzerScraper


class TestScraperInit:
    def test_known_election(self):
        scraper = StemwijzerScraper("gr2026", use_browser=False, use_api=False)
        assert scraper.config.slug == "gr2026"
        assert scraper.config.election_type == "municipal"

    def test_unknown_election_auto_config(self):
        scraper = StemwijzerScraper("xx9999", use_browser=False, use_api=False)
        assert scraper.config.slug == "xx9999"

    def test_election_config_object(self):
        config = ElectionConfig(
            slug="test",
            election_type="municipal",
            year=2026,
            app_url="https://test.stemwijzer.nl",
            data_url="https://test-data.stemwijzer.nl",
            context="2026TE",
        )
        scraper = StemwijzerScraper(config, use_browser=False, use_api=False)
        assert scraper.config.slug == "test"

    def test_cache_default(self):
        scraper = StemwijzerScraper("gr2026", use_browser=False, use_api=False)
        assert scraper.cache is not None

    def test_cache_disabled_with_none(self):
        scraper = StemwijzerScraper("gr2026", cache_dir=None, use_browser=False, use_api=False)
        assert scraper.cache is None

    def test_cache_custom_dir(self, tmp_path):
        cache_path = tmp_path / "my-cache"
        scraper = StemwijzerScraper(
            "gr2026", cache_dir=cache_path, use_browser=False, use_api=False
        )
        assert scraper.cache is not None
        assert scraper.cache.cache_dir == cache_path

    @pytest.mark.asyncio
    async def test_archived_election_disables_api_session_setup(self):
        scraper = StemwijzerScraper("tk2012", cache_dir=None, use_browser=False, use_api=True)
        async with scraper:
            assert scraper._api is None


class TestFindIndexEntry:
    @pytest.fixture
    def scraper(self):
        return StemwijzerScraper("gr2026", cache_dir=None, use_browser=False, use_api=False)

    @pytest.fixture
    def mock_index(self):
        return [
            ElectionIndexEntry(
                id=1,
                name="Groningen",
                source="GM0014-nl",
                remoteId="GM0014",
                language="nl",
                decrypt=True,
            ),
            ElectionIndexEntry(
                id=1,
                name="Groningen",
                source="GM0014-en",
                remoteId="GM0014",
                language="en",
                decrypt=True,
            ),
            ElectionIndexEntry(
                id=2,
                name="Almere",
                source="GM0034",
                remoteId="GM0034",
                language="nl",
                decrypt=True,
            ),
        ]

    @pytest.mark.asyncio
    async def test_exact_match_nl(self, scraper, mock_index):
        with patch.object(scraper, "fetch_index", new_callable=AsyncMock, return_value=mock_index):
            entry = await scraper._find_index_entry("GM0014", "nl")
            assert entry is not None
            assert entry.source == "GM0014-nl"
            assert entry.language == "nl"

    @pytest.mark.asyncio
    async def test_exact_match_en(self, scraper, mock_index):
        with patch.object(scraper, "fetch_index", new_callable=AsyncMock, return_value=mock_index):
            entry = await scraper._find_index_entry("GM0014", "en")
            assert entry is not None
            assert entry.source == "GM0014-en"
            assert entry.language == "en"

    @pytest.mark.asyncio
    async def test_nl_fallback_to_default(self, scraper, mock_index):
        """Dutch requests should fall back to default entry (no language suffix)."""
        with patch.object(scraper, "fetch_index", new_callable=AsyncMock, return_value=mock_index):
            entry = await scraper._find_index_entry("GM0034", "nl")
            assert entry is not None
            assert entry.source == "GM0034"

    @pytest.mark.asyncio
    async def test_unavailable_language_returns_none(self, scraper, mock_index):
        """Requesting a language that's not in the index returns None."""
        with patch.object(scraper, "fetch_index", new_callable=AsyncMock, return_value=mock_index):
            entry = await scraper._find_index_entry("GM0034", "en")
            assert entry is None

    @pytest.mark.asyncio
    async def test_unavailable_municipality_returns_none(self, scraper, mock_index):
        """Requesting a municipality not in the index returns None for non-nl."""
        with patch.object(scraper, "fetch_index", new_callable=AsyncMock, return_value=mock_index):
            entry = await scraper._find_index_entry("GM9999", "en")
            assert entry is None

    @pytest.mark.asyncio
    async def test_index_fetch_failure_constructs_guess(self, scraper):
        """If index fetch fails, construct a best-guess entry."""
        with patch.object(
            scraper, "fetch_index", new_callable=AsyncMock, side_effect=Exception("offline")
        ):
            entry = await scraper._find_index_entry("GM0014", "nl")
            assert entry is not None
            assert entry.source == "GM0014"
            assert entry.remoteId == "GM0014"

    @pytest.mark.asyncio
    async def test_index_fetch_failure_non_nl(self, scraper):
        """If index fetch fails for non-nl, construct entry with language suffix."""
        with patch.object(
            scraper, "fetch_index", new_callable=AsyncMock, side_effect=Exception("offline")
        ):
            entry = await scraper._find_index_entry("GM0014", "en")
            assert entry is not None
            assert entry.source == "GM0014-en"


class TestIndexCaching:
    @pytest.mark.asyncio
    async def test_index_cached_in_memory(self):
        """fetch_index() should cache results in memory."""
        scraper = StemwijzerScraper("gr2026", cache_dir=None, use_browser=False, use_api=False)
        mock_entries = [
            ElectionIndexEntry(
                id=1,
                name="Test",
                source="GM0001",
                remoteId="GM0001",
                language="nl",
                decrypt=True,
            ),
        ]
        scraper._index_cache = mock_entries
        result = await scraper.fetch_index()
        assert result is mock_entries


class TestExports:
    def test_known_elections_exported(self):
        assert "gr2026" in KNOWN_ELECTIONS
        assert "tk2006" in KNOWN_ELECTIONS
        assert KNOWN_ELECTIONS["gr2026"].election_type == "municipal"

    def test_election_config_exported(self):
        assert ElectionConfig is not None
        config = ElectionConfig(
            slug="test",
            election_type="test",
            year=2026,
            app_url="",
            data_url="",
            context="",
        )
        assert config.slug == "test"


class TestHistoricalFallback:
    @pytest.mark.asyncio
    async def test_single_contest_browser_payload_synthesizes_index(self):
        scraper = StemwijzerScraper("tk2023", cache_dir=None, use_browser=True, use_api=False)
        intercepted = InterceptedData(
            election_data={
                "tk2023": {
                    "parties": [{"id": 1, "name": "D66", "statements": []}],
                    "statements": [{"id": 101, "index": 1, "theme": "Wonen", "title": "Bouwen"}],
                    "shootoutStatements": [],
                }
            }
        )

        with patch.object(
            scraper,
            "_discover_via_browser",
            new_callable=AsyncMock,
            return_value=intercepted,
        ):
            index = await scraper.fetch_index()

        assert len(index) == 1
        assert index[0].source == "tk2023"
        assert index[0].remoteId == "tk2023"
        assert index[0].name == "Tweede Kamerverkiezing 2023"

    @pytest.mark.asyncio
    async def test_multi_jurisdiction_partial_browser_capture_raises(self):
        scraper = StemwijzerScraper("ps2023", cache_dir=None, use_browser=True, use_api=False)
        intercepted = InterceptedData(
            election_data={
                "zh": {
                    "parties": [{"id": 1, "name": "D66", "statements": []}],
                    "statements": [{"id": 101, "index": 1, "theme": "Wonen", "title": "Bouwen"}],
                    "shootoutStatements": [],
                }
            }
        )

        with (
            patch.object(
                scraper,
                "_discover_via_browser",
                new_callable=AsyncMock,
                return_value=intercepted,
            ),
            pytest.raises(APIScraperError, match="multi-jurisdiction"),
        ):
            await scraper.fetch_index()

    @pytest.mark.asyncio
    async def test_browser_scrape_normalizes_historical_payload_before_validation(self):
        scraper = StemwijzerScraper("eu2024", cache_dir=None, use_browser=True, use_api=False)
        intercepted = InterceptedData(
            election_data={
                "eu2024": {
                    "parties": [{"id": 3, "name": "Volt", "statements": []}],
                    "statements": [
                        {"id": 201, "index": 1, "theme": "Europa", "title": "Meer Europa"}
                    ],
                    "shootoutStatements": [],
                }
            }
        )

        with patch.object(
            scraper,
            "_discover_via_browser",
            new_callable=AsyncMock,
            return_value=intercepted,
        ):
            results = await scraper._scrape_via_browser()

        assert len(results) == 1
        assert results[0].votematch.remote_id == "eu2024"
        assert results[0].votematch.name == "Europese verkiezing 2024"
