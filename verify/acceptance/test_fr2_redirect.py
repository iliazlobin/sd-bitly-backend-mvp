"""FR2 — Redirect Short URL.

AC2: GET /{short_code} → 301 Location: {long_url} with Cache-Control: private, max-age=90.
     Non-existent code → 404. Each redirect increments the click counter.
"""

import httpx

from verify.acceptance.conftest import (
    assert_201,
    assert_301,
    assert_404,
    assert_json_200,
)


def _create_url(client: httpx.Client, long_url: str) -> dict:
    """Helper: create a short URL and return the parsed response."""
    return assert_201(client.post("/api/urls", json={"long_url": long_url}))


def test_redirect_returns_301_with_location(client: httpx.Client):
    """Create a short URL, then GET it → 301 with correct Location header."""
    url_obj = _create_url(client, "https://example.com/redirect-target")
    short_code = url_obj["short_code"]

    r = assert_301(client.get(f"/{short_code}"))
    assert r.headers["Location"] == "https://example.com/redirect-target"

    # Must include Cache-Control header with max-age=90
    cache_control = r.headers.get("Cache-Control", "")
    assert "max-age=90" in cache_control, f"Cache-Control missing max-age=90: {cache_control!r}"
    assert "private" in cache_control.lower(), f"Cache-Control missing private: {cache_control!r}"


def test_redirect_nonexistent_code_404(client: httpx.Client):
    """GET a nonexistent short code → 404."""
    assert_404(client.get("/nonexistent99"))


def test_redirect_increments_click_count(client: httpx.Client):
    """Each GET on a short code increments the click counter."""
    url_obj = _create_url(client, "https://example.com/count-clicks")
    short_code = url_obj["short_code"]

    # Redirect 3 times
    for _ in range(3):
        r = client.get(f"/{short_code}")
        assert r.status_code == 301, f"Redirect #{_}: expected 301, got {r.status_code}: {r.text}"

    # Verify click count via stats
    stats = assert_json_200(client.get(f"/api/urls/{short_code}/stats"))
    assert stats["clicks"] == 3, f"Expected 3 clicks after 3 redirects, got {stats['clicks']}"


def test_redirect_with_query_params(client: httpx.Client):
    """Redirect preserves the long URL's query string."""
    url_obj = _create_url(client, "https://example.com/search?q=bitly&sort=desc")
    short_code = url_obj["short_code"]

    r = assert_301(client.get(f"/{short_code}"))
    assert r.headers["Location"] == "https://example.com/search?q=bitly&sort=desc"
