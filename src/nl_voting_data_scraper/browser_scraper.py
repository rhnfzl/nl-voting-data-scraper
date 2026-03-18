"""Playwright-based browser automation fallback.

Two modes:
1. Network interception: load the page, capture API responses
2. DOM extraction: click through the UI (last resort)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Self

from nl_voting_data_scraper.bundle_extractor import (
    BROWSER_STATE_CAPTURE_SCRIPT,
    RUNTIME_CAPTURE_INIT_SCRIPT,
    build_single_contest_index_entry,
    extract_contests_from_browser_state,
    extract_contests_from_js_bundles,
    extract_contests_from_runtime_capture,
    normalize_contest_payload,
)
from nl_voting_data_scraper.config import ElectionConfig
from nl_voting_data_scraper.decoder import decode_response, extract_key_from_js

if TYPE_CHECKING:
    from types import TracebackType

logger = logging.getLogger(__name__)


@dataclass
class InterceptedData:
    """Data captured from network interception."""

    index: list[dict] = field(default_factory=list)
    election_data: dict = field(default_factory=dict)  # source -> data
    js_bundles: list[str] = field(default_factory=list)
    api_urls: list[str] = field(default_factory=list)
    decrypt_key: str | None = None
    runtime_payloads: list[str] = field(default_factory=list)
    browser_state: dict[str, Any] | None = None


class BrowserScraper:
    """Scrape StemWijzer via browser automation (Playwright)."""

    def __init__(self, config: ElectionConfig):
        self.config = config
        self._pw: Any = None
        self._browser: Any = None

    async def __aenter__(self) -> Self:
        try:
            from playwright.async_api import async_playwright
        except ImportError as err:
            raise ImportError(
                "Playwright is required for browser scraping. "
                "Install it with: pip install nl-voting-data-scraper[browser] "
                "&& playwright install chromium"
            ) from err
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    async def intercept_network(self, url: str | None = None) -> InterceptedData:
        """Load the StemWijzer page and intercept all API responses.

        This discovers API endpoints, captures data, and extracts encryption keys.
        """
        candidate_urls = [url] if url else list(self.config.browser_urls or (self.config.app_url,))
        last_result: InterceptedData | None = None
        last_error: Exception | None = None

        for candidate_url in candidate_urls:
            try:
                result = await self._intercept_single_url(candidate_url)
            except Exception as error:  # pragma: no cover - exercised through retries
                last_error = error
                logger.warning(f"Browser capture failed for {candidate_url}: {error}")
                continue

            if self._has_capture(result):
                return result
            last_result = result

        if last_result is not None:
            return last_result
        if last_error is not None:
            raise last_error
        return InterceptedData()

    async def _intercept_single_url(self, url: str) -> InterceptedData:
        result = InterceptedData()
        page = await self._browser.new_page()
        await page.add_init_script(script=RUNTIME_CAPTURE_INIT_SCRIPT)

        async def handle_response(response: Any) -> None:
            resp_url = response.url
            content_type = response.headers.get("content-type", "")

            # Capture JS bundles for key extraction
            if "javascript" in content_type or resp_url.endswith(".js"):
                try:
                    text = await response.text()
                    result.js_bundles.append(text)
                    key = extract_key_from_js(text)
                    if key:
                        result.decrypt_key = key
                        logger.info(f"Found decrypt key in JS bundle: {resp_url}")
                except Exception:
                    pass

            # Capture JSON/data responses
            if response.status == 200 and (
                "json" in content_type
                or "text/plain" in content_type
                or "octet-stream" in content_type
            ):
                try:
                    text = await response.text()
                    result.api_urls.append(resp_url)

                    # Try to decode the response
                    try:
                        decoded = decode_response(text, result.decrypt_key)
                        if isinstance(decoded, list) and decoded and "remoteId" in str(decoded[0]):
                            result.index = decoded
                            logger.info(f"Captured index from {resp_url}")
                        elif isinstance(decoded, dict) and "parties" in decoded:
                            source = resp_url.rstrip("/").split("/")[-1].replace(".json", "")
                            result.election_data[source] = decoded
                            logger.info(f"Captured election data: {source}")
                    except Exception:
                        pass
                except Exception:
                    pass

        page.on("response", handle_response)

        try:
            logger.info(f"Loading {url}...")
            await page.goto(url, wait_until="networkidle", timeout=30000)
            # Wait a bit for any lazy-loaded data
            await page.wait_for_timeout(3000)

            # Try clicking the start button to trigger data loading
            try:
                start_btn = page.locator(".start__button, [class*='start'] button, button")
                if await start_btn.first.is_visible(timeout=3000):
                    await start_btn.first.click()
                    await page.wait_for_timeout(3000)
            except Exception:
                pass

            try:
                runtime_payloads = await page.evaluate(
                    "() => globalThis.__stemwijzerParsedPayloads || []"
                )
                if isinstance(runtime_payloads, list):
                    result.runtime_payloads = [
                        item for item in runtime_payloads if isinstance(item, str)
                    ]
            except Exception:
                pass

            try:
                browser_state = await page.evaluate(BROWSER_STATE_CAPTURE_SCRIPT)
                if isinstance(browser_state, dict):
                    result.browser_state = browser_state
            except Exception:
                pass

        finally:
            await page.close()

        if not result.election_data:
            contests = extract_contests_from_runtime_capture(result.runtime_payloads)
            if not contests:
                contests = extract_contests_from_browser_state(result.browser_state, self.config)
            if not contests:
                contests = extract_contests_from_js_bundles(result.js_bundles)

            for contest in contests:
                normalized = normalize_contest_payload(contest, self.config)
                source = normalized["votematch"]["remote_id"]
                language = normalized["votematch"]["langcode"]
                source_name = source if language == "nl" else f"{source}-{language}"
                result.election_data[source_name] = normalized

        if not result.index and result.election_data and not self.config.has_municipalities:
            first_source, first_payload = next(iter(result.election_data.items()))
            entry = build_single_contest_index_entry(
                self.config,
                first_payload,
                source=first_source,
            )
            result.index = [entry.model_dump(by_alias=True)]

        return result

    def _has_capture(self, result: InterceptedData) -> bool:
        return bool(
            result.index
            or result.election_data
            or result.js_bundles
            or result.runtime_payloads
            or result.browser_state
        )

    async def discover_endpoints(self) -> InterceptedData:
        """Discover API endpoints and encryption keys by loading the frontend."""
        return await self.intercept_network()

    async def scrape_municipality_dom(self, url: str) -> dict[str, Any]:
        """Scrape a single municipality by clicking through the UI.

        This is the last-resort fallback that simulates user interaction.
        """
        page = await self._browser.new_page()
        statements: list[dict[str, Any]] = []
        parties_data: dict[str, Any] = {}

        try:
            await page.goto(url, wait_until="networkidle", timeout=30000)

            # Click start button
            start = page.locator(".start__button")
            await start.wait_for(timeout=10000)
            await start.click()
            await page.wait_for_timeout(2000)

            # Loop through statements
            while True:
                # Extract current statement
                try:
                    theme_el = page.locator(".statement__theme")
                    title_el = page.locator(".statement__title")

                    theme_count = await theme_el.count()
                    theme = await theme_el.text_content(timeout=3000) if theme_count else ""
                    title = await title_el.get_attribute("aria-label", timeout=3000) or ""
                    if not title:
                        title = await title_el.text_content(timeout=3000) or ""
                    title = re.sub(r"\s+", " ", title).strip()

                    statement = {"theme": theme.strip(), "title": title}

                    # Try to get more info
                    try:
                        more_info_btn = page.locator(".statement__tab-button--more-info")
                        if await more_info_btn.count():
                            await more_info_btn.click()
                            await page.wait_for_timeout(500)
                            tab_text = page.locator(".statement__tab-text")
                            info_text = await tab_text.text_content(timeout=2000)
                            statement["info"] = info_text.strip() if info_text else ""
                    except Exception:
                        pass

                    # Try to get party positions
                    try:
                        parties_btn = page.locator(".statement__tab-button--parties")
                        if await parties_btn.count():
                            await parties_btn.click()
                            await page.wait_for_timeout(500)
                            # Extract party positions from the panel
                    except Exception:
                        pass

                    statements.append(statement)
                except Exception as e:
                    logger.debug(f"Failed to extract statement: {e}")

                # Try to skip to next statement
                skip_btn = page.locator(".statement__skip")
                if await skip_btn.count() == 0:
                    break
                try:
                    await skip_btn.click()
                    await page.wait_for_timeout(1000)
                except Exception:
                    break

        finally:
            await page.close()

        return {"statements": statements, "parties": parties_data}
