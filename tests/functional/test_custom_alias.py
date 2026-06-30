"""Functional tests for FR4 — custom alias."""

from httpx import AsyncClient


class TestCustomAlias:
    async def test_create_with_custom_alias(self, client: AsyncClient) -> None:
        r = await client.post(
            "/api/urls",
            json={
                "long_url": "https://example.com/custom",
                "custom_alias": "myLink1",
            },
        )
        assert r.status_code == 201
        body = r.json()
        assert body["short_code"] == "myLink1"
        assert body["long_url"] == "https://example.com/custom"
        assert body["short_url"].endswith("/myLink1")

    async def test_custom_alias_redirects(self, client: AsyncClient) -> None:
        await client.post(
            "/api/urls",
            json={
                "long_url": "https://example.com/alias-redirect",
                "custom_alias": "goHere",
            },
        )

        r = await client.get("/goHere", follow_redirects=False)
        assert r.status_code == 301
        assert r.headers["Location"] == "https://example.com/alias-redirect"

    async def test_duplicate_alias_409(self, client: AsyncClient) -> None:
        alias = "myChannel"
        r1 = await client.post(
            "/api/urls",
            json={
                "long_url": "https://example.com/first",
                "custom_alias": alias,
            },
        )
        assert r1.status_code == 201

        r2 = await client.post(
            "/api/urls",
            json={
                "long_url": "https://example.com/second",
                "custom_alias": alias,
            },
        )
        assert r2.status_code == 409
        body = r2.json()
        assert "detail" in body

    async def test_invalid_alias_non_base62(self, client: AsyncClient) -> None:
        r = await client.post(
            "/api/urls",
            json={
                "long_url": "https://example.com/bad",
                "custom_alias": "has-dash!",
            },
        )
        assert r.status_code == 422

    async def test_invalid_alias_too_long(self, client: AsyncClient) -> None:
        r = await client.post(
            "/api/urls",
            json={
                "long_url": "https://example.com/long",
                "custom_alias": "a" * 21,
            },
        )
        assert r.status_code == 422

    async def test_invalid_alias_empty(self, client: AsyncClient) -> None:
        r = await client.post(
            "/api/urls",
            json={
                "long_url": "https://example.com/empty",
                "custom_alias": "",
            },
        )
        assert r.status_code == 422

    async def test_mixed_case_alias_preserved(self, client: AsyncClient) -> None:
        r = await client.post(
            "/api/urls",
            json={
                "long_url": "https://example.com/mixed",
                "custom_alias": "MyBrand",
            },
        )
        assert r.status_code == 201
        assert r.json()["short_code"] == "MyBrand"
