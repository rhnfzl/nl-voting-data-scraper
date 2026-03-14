"""HTTP-based API scraper: the primary (fast) scraping path.

Fetches data from StemWijzer data endpoints, handles base64 decoding
and optional AES decryption.
"""

from __future__ import annotations

import logging

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from nl_voting_data_scraper.cache import ScrapeCache
from nl_voting_data_scraper.config import DEFAULT_HEADERS, DATA_URL_PATTERNS, ElectionConfig
from nl_voting_data_scraper.decoder import DecodeError, decode_response
from nl_voting_data_scraper.models import ElectionData, ElectionIndexEntry
from nl_voting_data_scraper.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)


class APIScraperError(Exception):
    """API scraping failed."""


class APIScraper:
    """Fetch StemWijzer data via HTTP API endpoints."""

    def __init__(
        self,
        config: ElectionConfig,
        rate_limiter: RateLimiter | None = None,
        cache: ScrapeCache | None = None,
        decrypt_key: str | None = None,
    ):
        self.config = config
        self.rate_limiter = rate_limiter or RateLimiter()
        self.cache = cache
        self.decrypt_key = decrypt_key
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            headers={
                **DEFAULT_HEADERS,
                "Referer": self.config.app_url + "/",
                "Origin": self.config.app_url,
            },
            timeout=30.0,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise RuntimeError("APIScraper must be used as async context manager")
        return self._client

    async def probe_data_url(self) -> str | None:
        """Try known URL patterns to find a working data endpoint.

        Returns the working base URL or None.
        """
        urls_to_try = [self.config.data_url]
        for pattern in DATA_URL_PATTERNS:
            url = pattern.format(slug=self.config.slug)
            if url not in urls_to_try:
                urls_to_try.append(url)

        for url in urls_to_try:
            try:
                await self.rate_limiter.acquire()
                resp = await self.client.get(url + "/index.json")
                if resp.status_code == 200:
                    logger.info(f"Found working data URL: {url}")
                    return url
                # 403 with content might still be valid (base64 encoded)
                if resp.status_code == 200 or (resp.status_code == 403 and len(resp.content) > 100):
                    try:
                        decode_response(resp.text, self.decrypt_key)
                        logger.info(f"Found working data URL (encoded): {url}")
                        return url
                    except DecodeError:
                        pass
            except httpx.HTTPError as e:
                logger.debug(f"Probe failed for {url}: {e}")
                continue

        return None

    async def fetch_index(self) -> list[ElectionIndexEntry]:
        """Fetch the election index (list of municipalities/elections)."""
        url = self.config.data_url + "/index.json"
        await self.rate_limiter.acquire()
        resp = await self.client.get(url)
        resp.raise_for_status()

        data = decode_response(resp.text, self.decrypt_key)
        if not isinstance(data, list):
            raise APIScraperError(f"Index is not a list: {type(data)}")

        return [ElectionIndexEntry.model_validate(entry) for entry in data]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, max=30))
    async def fetch_election_data(
        self, entry: ElectionIndexEntry
    ) -> ElectionData:
        """Fetch data for a single election/municipality."""
        # Check cache first
        if self.cache and self.cache.has(self.config.slug, entry.source):
            logger.info(f"Cache hit: {entry.source}")
            cached = self.cache.get(self.config.slug, entry.source)
            if cached:
                return cached

        url = f"{self.config.data_url}/{entry.source}/data.json"
        await self.rate_limiter.acquire()

        logger.info(f"Fetching {entry.name} ({entry.source})...")
        resp = await self.client.get(url)
        resp.raise_for_status()

        key = self.decrypt_key if entry.decrypt else None
        data = decode_response(resp.text, key)

        if not isinstance(data, dict):
            raise APIScraperError(f"Election data is not a dict: {type(data)}")

        result = ElectionData.model_validate(data)

        # Cache the raw decoded data
        if self.cache:
            self.cache.put(self.config.slug, entry.source, data)

        return result

    async def fetch_all(
        self,
        municipalities: list[str] | None = None,
    ) -> list[ElectionData]:
        """Fetch all election data.

        Args:
            municipalities: Optional list of GM codes to filter (e.g. ["GM0014", "GM0034"]).
        """
        index = await self.fetch_index()

        if municipalities:
            gm_set = set(municipalities)
            index = [e for e in index if e.remoteId in gm_set]
            logger.info(f"Filtered to {len(index)} entries matching {municipalities}")

        results = []
        for i, entry in enumerate(index, 1):
            try:
                data = await self.fetch_election_data(entry)
                results.append(data)
                logger.info(f"  [{i}/{len(index)}] {entry.name} ({entry.source}) OK")
            except Exception as e:
                logger.error(f"  [{i}/{len(index)}] {entry.name} ({entry.source}) FAILED: {e}")

        return results
