"""Tests for file-based cache."""

from nl_voting_data_scraper.cache import ScrapeCache


class TestScrapeCache:
    def test_put_and_get(self, tmp_cache, sample_municipality):
        cache = ScrapeCache(tmp_cache)
        cache.put("gr2026", "GM0415", sample_municipality)
        assert cache.has("gr2026", "GM0415")

        result = cache.get_raw("gr2026", "GM0415")
        assert result is not None
        assert result["votematch"]["remote_id"] == "GM0415"

    def test_get_missing(self, tmp_cache):
        cache = ScrapeCache(tmp_cache)
        assert not cache.has("gr2026", "GM9999")
        assert cache.get_raw("gr2026", "GM9999") is None

    def test_list_cached(self, tmp_cache, sample_municipality):
        cache = ScrapeCache(tmp_cache)
        cache.put("gr2026", "GM0001", sample_municipality)
        cache.put("gr2026", "GM0002", sample_municipality)

        cached = cache.list_cached("gr2026")
        assert "GM0001" in cached
        assert "GM0002" in cached

    def test_clear_election(self, tmp_cache, sample_municipality):
        cache = ScrapeCache(tmp_cache)
        cache.put("gr2026", "GM0001", sample_municipality)
        cache.put("tk2025", "national", sample_municipality)

        count = cache.clear("gr2026")
        assert count >= 1
        assert not cache.has("gr2026", "GM0001")
        assert cache.has("tk2025", "national")

    def test_clear_all(self, tmp_cache, sample_municipality):
        cache = ScrapeCache(tmp_cache)
        cache.put("gr2026", "GM0001", sample_municipality)
        cache.put("tk2025", "national", sample_municipality)

        cache.clear()
        assert not cache.has("gr2026", "GM0001")
        assert not cache.has("tk2025", "national")
