"""Playwright-based browser automation fallback.

Two modes:
1. Network interception: load the page, capture API responses
2. DOM extraction: click through the UI (last resort)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from nl_voting_data_scraper.config import ElectionConfig
from nl_voting_data_scraper.decoder import decode_response, extract_key_from_js

logger = logging.getLogger(__name__)


@dataclass
class InterceptedData:
    """Data captured from network interception."""

    index: list[dict] = field(default_factory=list)
    election_data: dict = field(default_factory=dict)  # source -> data
    js_bundles: list[str] = field(default_factory=list)
    api_urls: list[str] = field(default_factory=list)
    decrypt_key: str | None = None


class BrowserScraper:
    """Scrape StemWijzer via browser automation (Playwright)."""

    def __init__(self, config: ElectionConfig):
        self.config = config
        self._pw = None
        self._browser = None

    async def __aenter__(self):
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError(
                "Playwright is required for browser scraping. "
                "Install it with: pip install nl-voting-data-scraper[browser] "
                "&& playwright install chromium"
            )
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True)
        return self

    async def __aexit__(self, *args):
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    async def intercept_network(self, url: str | None = None) -> InterceptedData:
        """Load the StemWijzer page and intercept all API responses.

        This discovers API endpoints, captures data, and extracts encryption keys.
        """
        url = url or self.config.app_url
        result = InterceptedData()
        page = await self._browser.new_page()

        async def handle_response(response):
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

        finally:
            await page.close()

        return result

    async def discover_endpoints(self) -> InterceptedData:
        """Discover API endpoints and encryption keys by loading the frontend."""
        return await self.intercept_network()

    async def scrape_municipality_dom(self, url: str) -> dict:
        """Scrape a single municipality by clicking through the UI.

        This is the last-resort fallback that simulates user interaction.
        """
        page = await self._browser.new_page()
        statements = []
        parties_data = {}

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

                    theme = await theme_el.text_content(timeout=3000) if await theme_el.count() else ""
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
                            info_text = await page.locator(".statement__tab-text").text_content(timeout=2000)
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
