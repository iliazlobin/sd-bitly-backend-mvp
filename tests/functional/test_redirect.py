"""Functional tests for GET /{short_code} — redirect."""

from httpx import AsyncClient


async def _create(client: AsyncClient, long_url: str) -> dict:
    r = await client.post("/api/urls", json={"long_url": long_url})
    assert r.status_code == 201
    return r.json()


class TestRedirect:
    async def test_redirect_301_with_location(self, client: AsyncClient) -> None:
        url_obj = await _create(client, "https://example.com/redirect-target")
        short_code = url_obj["short_code"]

        r = await client.get(f"/{short_code}", follow_redirects=False)
        assert r.status_code == 301
        assert r.headers["Location"] == "https://example.com/redirect-target"

        cache_control = r.headers.get("Cache-Control", "")
        assert "max-age=90" in cache_control
        assert "private" in cache_control.lower()

    async def test_nonexistent_404(self, client: AsyncClient) -> None:
        r = await client.get("/nonexistent99")
        assert r.status_code == 404

    async def test_increments_click_count(self, client: AsyncClient) -> None:
        url_obj = await _create(client, "https://example.com/count-clicks")
        short_code = url_obj["short_code"]

        # Redirect 3 times.
        for _ in range(3):
            r = await client.get(f"/{short_code}", follow_redirects=False)
            assert r.status_code == 301

        # Verify via stats.
        r = await client.get(f"/api/urls/{short_code}/stats")
        assert r.status_code == 200
        stats = r.json()
        assert stats["clicks"] == 3

    async def test_preserves_query_string(self, client: AsyncClient) -> None:
        url_obj = await _create(client, "https://example.com/search?q=bitly&sort=desc")
        short_code = url_obj["short_code"]

        r = await client.get(f"/{short_code}", follow_redirects=False)
        assert r.status_code == 301
        assert r.headers["Location"] == "https://example.com/search?q=bitly&sort=desc"

    async def test_invalid_short_code_format_404(self, client: AsyncClient) -> None:
        """Short codes with invalid characters → 404 (don't hit the DB)."""
        r = await client.get("/has-dash!")
        assert r.status_code == 404
