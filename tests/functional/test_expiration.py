"""Functional tests for FR5 — URL expiration."""

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient


async def _create(client: AsyncClient, long_url: str, **kwargs) -> dict:
    r = await client.post("/api/urls", json={"long_url": long_url, **kwargs})
    assert r.status_code == 201
    return r.json()


class TestExpiration:
    async def test_create_with_expires_at(self, client: AsyncClient) -> None:
        future = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        body = await _create(client, "https://example.com/expiring", expires_at=future)
        assert body["expires_at"] is not None

    async def test_expired_link_returns_410(self, client: AsyncClient) -> None:
        past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        r = await client.post(
            "/api/urls",
            json={
                "long_url": "https://example.com/already-expired",
                "expires_at": past,
            },
        )
        assert r.status_code == 201
        short_code = r.json()["short_code"]

        r2 = await client.get(f"/{short_code}", follow_redirects=False)
        assert r2.status_code == 410

    async def test_stats_shows_expires_at(self, client: AsyncClient) -> None:
        future = (datetime.now(UTC) + timedelta(days=7)).isoformat()
        body = await _create(client, "https://example.com/will-expire", expires_at=future)
        short_code = body["short_code"]

        r = await client.get(f"/api/urls/{short_code}/stats")
        assert r.status_code == 200
        assert r.json()["expires_at"] is not None

    async def test_stats_without_expiry_has_null(self, client: AsyncClient) -> None:
        body = await _create(client, "https://example.com/permanent")
        short_code = body["short_code"]

        r = await client.get(f"/api/urls/{short_code}/stats")
        assert r.status_code == 200
        assert r.json()["expires_at"] is None

    async def test_non_expired_link_redirects(self, client: AsyncClient) -> None:
        future = (datetime.now(UTC) + timedelta(days=30)).isoformat()
        body = await _create(client, "https://example.com/still-alive", expires_at=future)
        short_code = body["short_code"]

        r = await client.get(f"/{short_code}", follow_redirects=False)
        assert r.status_code == 301
        assert r.headers["Location"] == "https://example.com/still-alive"

    async def test_expired_link_stats_still_accessible(self, client: AsyncClient) -> None:
        past = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
        r = await client.post(
            "/api/urls",
            json={
                "long_url": "https://example.com/expired-but-stats",
                "expires_at": past,
            },
        )
        assert r.status_code == 201
        short_code = r.json()["short_code"]

        # Redirect returns 410
        r2 = await client.get(f"/{short_code}", follow_redirects=False)
        assert r2.status_code == 410

        # Stats still accessible
        r3 = await client.get(f"/api/urls/{short_code}/stats")
        assert r3.status_code == 200
        stats = r3.json()
        assert stats["short_code"] == short_code
        assert stats["expires_at"] is not None

    async def test_nonexistent_not_expired(self, client: AsyncClient) -> None:
        """A nonexistent code returns 404, not 410."""
        r = await client.get("/expiredButNotReal")
        assert r.status_code == 404
