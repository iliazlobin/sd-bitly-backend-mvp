"""Functional tests for GET /api/urls/{short_code}/stats."""

from httpx import AsyncClient


async def _create(client: AsyncClient, long_url: str, **kwargs) -> dict:
    r = await client.post("/api/urls", json={"long_url": long_url, **kwargs})
    assert r.status_code == 201
    return r.json()


class TestStats:
    async def test_returns_metadata(self, client: AsyncClient) -> None:
        url_obj = await _create(client, "https://example.com/stats-test")
        short_code = url_obj["short_code"]

        r = await client.get(f"/api/urls/{short_code}/stats")
        assert r.status_code == 200
        stats = r.json()

        assert stats["short_code"] == short_code
        assert stats["long_url"] == "https://example.com/stats-test"
        assert "clicks" in stats
        assert "created_at" in stats
        assert "expires_at" in stats

    async def test_clicks_match_redirect_count(self, client: AsyncClient) -> None:
        url_obj = await _create(client, "https://example.com/stats-clicks")
        short_code = url_obj["short_code"]

        for _ in range(5):
            r = await client.get(f"/{short_code}", follow_redirects=False)
            assert r.status_code == 301

        r = await client.get(f"/api/urls/{short_code}/stats")
        assert r.status_code == 200
        assert r.json()["clicks"] == 5

    async def test_zero_clicks_after_create(self, client: AsyncClient) -> None:
        url_obj = await _create(client, "https://example.com/zero-clicks")
        short_code = url_obj["short_code"]

        r = await client.get(f"/api/urls/{short_code}/stats")
        assert r.status_code == 200
        assert r.json()["clicks"] == 0

    async def test_nonexistent_404(self, client: AsyncClient) -> None:
        r = await client.get("/api/urls/nonexistent99/stats")
        assert r.status_code == 404
