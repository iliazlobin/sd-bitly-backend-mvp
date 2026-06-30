"""Functional tests for POST /api/urls — create short URL."""

import re

from httpx import AsyncClient


async def _create(client: AsyncClient, long_url: str, **kwargs) -> dict:
    """Helper: create a short URL and return parsed JSON."""
    payload = {"long_url": long_url, **kwargs}
    r = await client.post("/api/urls", json=payload)
    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"
    return r.json()


class TestCreateURL:
    async def test_creates_with_valid_url(self, client: AsyncClient) -> None:
        body = await _create(client, "https://example.com/some/path")
        assert re.fullmatch(r"[0-9a-zA-Z]{7}", body["short_code"])
        assert body["short_url"].endswith(f"/{body['short_code']}")
        assert body["long_url"] == "https://example.com/some/path"
        assert body["clicks"] == 0
        assert body["expires_at"] is None
        assert "created_at" in body

    async def test_canonicalizes_url(self, client: AsyncClient) -> None:
        body = await _create(client, "HTTPS://EXAMPLE.COM:443/path?q=1#section")
        assert body["long_url"] == "https://example.com/path?q=1"

    async def test_strips_default_port_80(self, client: AsyncClient) -> None:
        body = await _create(client, "http://example.com:80/page")
        assert body["long_url"] == "http://example.com/page"

    async def test_preserves_query_string(self, client: AsyncClient) -> None:
        body = await _create(client, "http://example.com/search?q=hello&page=1")
        assert body["long_url"] == "http://example.com/search?q=hello&page=1"

    async def test_missing_long_url_422(self, client: AsyncClient) -> None:
        r = await client.post("/api/urls", json={})
        assert r.status_code == 422

    async def test_empty_long_url_422(self, client: AsyncClient) -> None:
        r = await client.post("/api/urls", json={"long_url": ""})
        assert r.status_code == 422

    async def test_invalid_url_422(self, client: AsyncClient) -> None:
        r = await client.post("/api/urls", json={"long_url": "not-a-url"})
        assert r.status_code == 422

    async def test_no_scheme_422(self, client: AsyncClient) -> None:
        r = await client.post("/api/urls", json={"long_url": "example.com/path"})
        assert r.status_code == 422

    async def test_same_url_different_codes(self, client: AsyncClient) -> None:
        """Idempotency: same long_url twice → two different short codes."""
        r1 = await _create(client, "https://example.com/dup")
        r2 = await _create(client, "https://example.com/dup")
        assert r1["short_code"] != r2["short_code"]
        assert re.fullmatch(r"[0-9a-zA-Z]{7}", r1["short_code"])
        assert re.fullmatch(r"[0-9a-zA-Z]{7}", r2["short_code"])

    async def test_created_at_is_iso8601(self, client: AsyncClient) -> None:
        body = await _create(client, "https://example.com/time")
        # Should be an ISO 8601 timestamp string
        assert "T" in body["created_at"] or "+" in body["created_at"]
