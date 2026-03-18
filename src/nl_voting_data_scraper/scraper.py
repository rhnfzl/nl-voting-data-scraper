"""Main orchestrator: tries API first, falls back to browser automation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from nl_voting_data_scraper.browser_scraper import InterceptedData

from nl_voting_data_scraper.api_scraper import APIScraper, APIScraperError
from nl_voting_data_scraper.bundle_extractor import (
    build_single_contest_index_entry,
    normalize_contest_payload,
)
from nl_voting_data_scraper.cache import ScrapeCache
from nl_voting_data_scraper.config import (
    ElectionConfig,
    build_custom_election,
    get_election_config,
)
from nl_voting_data_scraper.models import ElectionData, ElectionIndexEntry
from nl_voting_data_scraper.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

# Sentinel to distinguish "not passed" from None
_UNSET = object()


class StemwijzerScraper:
    """Main scraper: API-first with browser fallback.

    Usage:
        async with StemwijzerScraper("gr2026") as scraper:
            # Scrape all municipalities
            results = await scraper.scrape()

            # Scrape specific municipality
            result = await scraper.scrape_one("GM0014")
    """

    def __init__(
        self,
        election: str | ElectionConfig,
        rate_limit: float = 2.0,
        cache_dir: str | Path | None | object = _UNSET,
        use_browser: bool = True,
        use_api: bool = True,
    ):
        if isinstance(election, str):
            config = get_election_config(election)
            if not config:
                config = build_custom_election(election)
                logger.info(f"Using auto-detected config for '{election}'")
            self.config = config
        else:
            self.config = election

        self.rate_limiter = RateLimiter(requests_per_second=rate_limit)

        # cache_dir=None explicitly disables caching; omitting it uses the default
        if cache_dir is _UNSET:
            self.cache: ScrapeCache | None = ScrapeCache(Path(".cache") / "nl-voting-data-scraper")
        elif cache_dir is not None:
            self.cache = ScrapeCache(cache_dir)  # type: ignore[arg-type]
        else:
            self.cache = None

        self.use_browser = use_browser
        self.use_api = use_api
        self._decrypt_key: str | None = None
        self._api: APIScraper | None = None
        self._index_cache: list[ElectionIndexEntry] | None = None

    async def __aenter__(self) -> Self:
        if self.use_api and self.config.supports_api:
            self._api = APIScraper(self.config, self.rate_limiter, self.cache, self._decrypt_key)
            await self._api.__aenter__()
        return self

    async def __aexit__(self, *args: object) -> None:
        if self._api:
            await self._api.__aexit__(*args)

    async def scrape(
        self,
        municipalities: list[str] | None = None,
        languages: list[str] | None = None,
    ) -> list[ElectionData]:
        """Scrape election data.

        Args:
            municipalities: Specific GM codes (e.g. ["GM0014"]). None = all.
            languages: Language codes to include (e.g. ["nl", "en"]). None = all available.
        """
        # Try API first
        if self.use_api and self._api:
            try:
                results = await self._api.fetch_all(municipalities, languages)
                if results:
                    logger.info(f"API scraping complete: {len(results)} entries")
                    return results
            except Exception as e:
                logger.warning(f"API scraping failed: {e}")

        # Fall back to browser
        if self.use_browser:
            results = await self._scrape_via_browser(municipalities)
            if languages:
                lang_set = set(languages)
                results = [r for r in results if r.votematch.langcode in lang_set]
            return results

        raise APIScraperError("All scraping methods failed")

    async def scrape_one(
        self,
        remote_id: str,
        language: str = "nl",
    ) -> ElectionData | None:
        """Scrape a single municipality/election.

        Returns None if the requested language is not available for this municipality.
        Raises APIScraperError if scraping fails for other reasons.
        """
        # Look up the correct source from the index (handles GM0014-nl vs GM0034)
        entry = await self._find_index_entry(remote_id, language)
        if entry is None:
            return None

        # Check cache
        if self.cache:
            cached = self.cache.get(self.config.slug, entry.source)
            if cached:
                logger.info(f"Cache hit: {entry.source}")
                return cached

        # Try API
        if self.use_api and self._api:
            try:
                return await self._api.fetch_election_data(entry)
            except Exception as e:
                logger.warning(f"API fetch failed for {entry.source}: {e}")

        # Fall back to browser
        if self.use_browser:
            results = await self._scrape_via_browser([remote_id])
            if results:
                # Filter for the requested language
                for r in results:
                    if r.votematch.langcode == language:
                        return r
                # If no language match, return first result only if language is "nl"
                # (some municipalities have a single entry without explicit language)
                if language == "nl":
                    return results[0]
                return None

        raise APIScraperError(f"Failed to scrape {entry.source}")

    async def _find_index_entry(
        self,
        remote_id: str,
        language: str = "nl",
    ) -> ElectionIndexEntry | None:
        """Find the correct index entry for a municipality and language.

        Returns None if the requested language is not available. Falls back to
        the default language entry only when requesting "nl" (since some
        municipalities have a single entry without an explicit language suffix).
        """
        try:
            index = await self.fetch_index()
        except Exception:
            # Index fetch failed entirely - construct a best-guess entry
            # so scrape_one can attempt to fetch the data directly
            source = f"{remote_id}-{language}" if language != "nl" else remote_id
            return ElectionIndexEntry(
                id=0,
                name=remote_id,
                source=source,
                remoteId=remote_id,
                language=language,
                decrypt=True,
            )

        # Exact match on remoteId + language
        for e in index:
            if e.remoteId == remote_id and e.language == language:
                return e

        # For Dutch, also accept entries without explicit language suffix
        # (e.g. "GM0034" with language="nl")
        if language == "nl":
            for e in index:
                if e.remoteId == remote_id:
                    return e

        # Language not available for this municipality
        return None

    async def fetch_index(self) -> list[ElectionIndexEntry]:
        """Fetch the election index.

        Results are cached in memory for the lifetime of the scraper instance.
        """
        if self._index_cache is not None:
            return self._index_cache

        if self.use_api and self._api:
            try:
                self._index_cache = await self._api.fetch_index()
                return self._index_cache
            except Exception as e:
                logger.warning(f"API index fetch failed: {e}")

        # Fall back to browser discovery
        if self.use_browser:
            intercepted = await self._discover_via_browser()
            if intercepted.index:
                self._index_cache = [
                    ElectionIndexEntry.model_validate(e) for e in intercepted.index
                ]
                return self._index_cache
            if intercepted.election_data and not self.config.has_municipalities:
                self._index_cache = [
                    build_single_contest_index_entry(
                        self.config,
                        data,
                        source=source,
                    )
                    for source, data in intercepted.election_data.items()
                ]
                return self._index_cache
            if intercepted.election_data and self.config.has_municipalities:
                raise APIScraperError(
                    "Browser captured contest payloads but could not discover the index for "
                    f"multi-jurisdiction election {self.config.slug}"
                )

        raise APIScraperError("Failed to fetch index")

    async def discover_endpoints(self) -> dict[str, Any]:
        """Discover API endpoints (useful for debugging)."""
        config_info = {
            "slug": self.config.slug,
            "data_url": self.config.data_url,
            "supports_api": self.config.supports_api,
            "browser_urls": list(self.config.browser_urls),
        }
        info: dict[str, Any] = {"config": config_info}

        if self.use_api and self._api:
            working_url = await self._api.probe_data_url()
            info["api_url"] = working_url

        if self.use_browser:
            intercepted = await self._discover_via_browser()
            info["discovered_urls"] = intercepted.api_urls
            info["decrypt_key"] = intercepted.decrypt_key
            info["index_entries"] = len(intercepted.index)
            info["captured_data"] = list(intercepted.election_data.keys())
            info["runtime_payloads"] = len(intercepted.runtime_payloads)

        return info

    async def _scrape_via_browser(
        self, municipalities: list[str] | None = None
    ) -> list[ElectionData]:
        """Scrape using Playwright browser automation."""
        intercepted = await self._discover_via_browser()

        if intercepted.decrypt_key:
            self._decrypt_key = intercepted.decrypt_key
            logger.info("Discovered decrypt key via browser")

        results = []
        for source, data in intercepted.election_data.items():
            if municipalities:
                gm_code = source.split("-")[0] if "-" in source else source
                if gm_code not in municipalities:
                    continue
            try:
                normalized = normalize_contest_payload(data, self.config, source=source)
                result = ElectionData.model_validate(normalized)
                results.append(result)
                if self.cache:
                    self.cache.put(self.config.slug, source, normalized)
            except Exception as e:
                logger.error(f"Failed to parse browser data for {source}: {e}")

        return results

    async def _discover_via_browser(self) -> InterceptedData:
        """Use Playwright to discover endpoints and capture data."""
        from nl_voting_data_scraper.browser_scraper import BrowserScraper

        async with BrowserScraper(self.config) as browser:
            return await browser.discover_endpoints()
