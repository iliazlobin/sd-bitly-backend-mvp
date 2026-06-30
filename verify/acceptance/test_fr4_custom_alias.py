"""FR4 — Custom Alias.

AC4: POST /api/urls with custom_alias → 201, short_code == alias.
     Duplicate alias → 409 Conflict.
     Invalid alias (non-base62 chars or >20 chars) → 422.
"""
import httpx

from verify.acceptance.conftest import assert_201, assert_409, assert_422


def _create_url(client: httpx.Client, long_url: str, **kwargs) -> dict:
    """Helper: create a short URL and return the parsed response."""
    payload = {"long_url": long_url, **kwargs}
    return assert_201(client.post("/api/urls", json=payload))


def test_create_with_custom_alias(client: httpx.Client):
    """POST with valid custom_alias → 201, short_code matches the alias."""
    body = assert_201(client.post("/api/urls", json={
        "long_url": "https://example.com/custom",
        "custom_alias": "myLink1",
    }))
    assert body["short_code"] == "myLink1"
    assert body["long_url"] == "https://example.com/custom"
    assert body["short_url"].endswith("/myLink1")


def test_custom_alias_redirects(client: httpx.Client):
    """A custom alias redirects correctly."""
    assert_201(client.post("/api/urls", json={
        "long_url": "https://example.com/alias-redirect",
        "custom_alias": "goHere",
    }))

    r = client.get("/goHere")
    assert r.status_code == 301
    assert r.headers["Location"] == "https://example.com/alias-redirect"


def test_duplicate_alias_409(client: httpx.Client):
    """Creating with an already-taken alias → 409 Conflict."""
    alias = "myChannel"
    assert_201(client.post("/api/urls", json={
        "long_url": "https://example.com/first",
        "custom_alias": alias,
    }))

    body = assert_409(client.post("/api/urls", json={
        "long_url": "https://example.com/second",
        "custom_alias": alias,
    }))
    assert "detail" in body
    # Error message should reference the alias or indicate it's taken
    error_msg = str(body).lower()
    assert alias.lower() in error_msg or "taken" in error_msg or "exists" in error_msg, (
        f"409 error does not mention the alias: {body}"
    )


def test_invalid_alias_non_base62(client: httpx.Client):
    """custom_alias with non-base62 chars → 422."""
    assert_422(client.post("/api/urls", json={
        "long_url": "https://example.com/bad",
        "custom_alias": "has-dash!",
    }))


def test_invalid_alias_too_long(client: httpx.Client):
    """custom_alias > 20 chars → 422."""
    assert_422(client.post("/api/urls", json={
        "long_url": "https://example.com/long",
        "custom_alias": "a" * 21,
    }))


def test_invalid_alias_empty(client: httpx.Client):
    """custom_alias as empty string → 422."""
    assert_422(client.post("/api/urls", json={
        "long_url": "https://example.com/empty",
        "custom_alias": "",
    }))


def test_mixed_case_alias_normalized(client: httpx.Client):
    """Custom alias with uppercase is preserved as-is (alias is user-chosen)."""
    body = assert_201(client.post("/api/urls", json={
        "long_url": "https://example.com/mixed",
        "custom_alias": "MyBrand",
    }))
    assert body["short_code"] == "MyBrand"
