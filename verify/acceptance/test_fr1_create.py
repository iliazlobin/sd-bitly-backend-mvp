"""FR1 — Create Short URL.

AC1: POST /api/urls with valid long_url → 201 with short_code (7 base62 chars),
     short_url, long_url, clicks=0, created_at, expires_at=null.
     URL is canonicalized (lowercase scheme+host, strip default ports and fragment).
     Missing/invalid long_url → 422. Same long_url twice produces different codes.
"""

import re

import httpx

from verify.acceptance.conftest import assert_201, assert_422


def test_create_short_url_success(client: httpx.Client):
    """POST /api/urls with valid long_url → 201 with correct shape."""
    body = assert_201(
        client.post(
            "/api/urls",
            json={
                "long_url": "https://example.com/some/path",
            },
        )
    )

    assert "short_code" in body
    assert "short_url" in body
    assert "long_url" in body
    assert "clicks" in body
    assert "created_at" in body
    assert "expires_at" in body

    # short_code must be exactly 7 base62 chars
    assert re.fullmatch(
        r"[0-9a-zA-Z]{7}", body["short_code"]
    ), f"short_code {body['short_code']!r} does not match 7-char base62"

    # short_url must end with /{short_code}
    assert body["short_url"].endswith(
        f"/{body['short_code']}"
    ), f"short_url {body['short_url']!r} does not end with /{body['short_code']}"

    # long_url is canonicalized
    assert body["long_url"] == "https://example.com/some/path"

    assert body["clicks"] == 0
    assert body["expires_at"] is None


def test_create_canonicalizes_url(client: httpx.Client):
    """URL canonicalization: lowercase scheme+host, strip default ports, strip fragments."""
    body = assert_201(
        client.post(
            "/api/urls",
            json={
                "long_url": "HTTPS://EXAMPLE.COM:443/path?q=1#section",
            },
        )
    )
    assert body["long_url"] == "https://example.com/path?q=1"


def test_create_strips_default_port_80(client: httpx.Client):
    """HTTP default port 80 is stripped."""
    body = assert_201(
        client.post(
            "/api/urls",
            json={
                "long_url": "http://example.com:80/page",
            },
        )
    )
    assert body["long_url"] == "http://example.com/page"


def test_create_preserves_query_string(client: httpx.Client):
    """Query parameters are preserved in canonicalization."""
    body = assert_201(
        client.post(
            "/api/urls",
            json={
                "long_url": "http://example.com/search?q=hello&page=1",
            },
        )
    )
    assert body["long_url"] == "http://example.com/search?q=hello&page=1"


def test_create_missing_long_url(client: httpx.Client):
    """Missing long_url → 422."""
    assert_422(client.post("/api/urls", json={}))


def test_create_empty_long_url(client: httpx.Client):
    """Empty long_url → 422."""
    assert_422(client.post("/api/urls", json={"long_url": ""}))


def test_create_invalid_url(client: httpx.Client):
    """Unparseable long_url → 422."""
    assert_422(client.post("/api/urls", json={"long_url": "not-a-url"}))


def test_create_invalid_url_no_scheme(client: httpx.Client):
    """long_url without scheme → 422."""
    assert_422(client.post("/api/urls", json={"long_url": "example.com/path"}))


def test_same_long_url_different_codes(client: httpx.Client):
    """Creating the same long_url twice produces two different short codes.
    No dedup in MVP — each POST is a new short link.
    """
    r1 = assert_201(
        client.post(
            "/api/urls",
            json={
                "long_url": "https://example.com/dup",
            },
        )
    )
    r2 = assert_201(
        client.post(
            "/api/urls",
            json={
                "long_url": "https://example.com/dup",
            },
        )
    )
    assert (
        r1["short_code"] != r2["short_code"]
    ), f"Same long_url produced same code {r1['short_code']!r}"
    # Both should be valid 7-char codes
    for r in (r1, r2):
        assert re.fullmatch(r"[0-9a-zA-Z]{7}", r["short_code"])


def test_rate_limit_exceeded(client: httpx.Client):
    """Exceeding rate limit (10 req/s per IP) → 429 with Retry-After."""
    # Send 15 rapid requests; system may return 429 after the limit is hit
    statuses = []
    for _ in range(15):
        r = client.post(
            "/api/urls",
            json={
                "long_url": "https://example.com/ratelimit",
            },
        )
        statuses.append(r.status_code)

    # At least one should be 429 if rate limiting is active
    assert (
        429 in statuses
    ), f"Expected at least one 429 among {statuses}; rate limiting may not be active"

    # Verify the 429 response includes Retry-After
    for r_status in (r for r in statuses if r == 429):
        r = client.post(
            "/api/urls",
            json={
                "long_url": "https://example.com/ratelimit",
            },
        )
        if r.status_code == 429:
            assert "Retry-After" in r.headers, "429 did not include Retry-After header"
            break
