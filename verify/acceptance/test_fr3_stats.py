"""FR3 — Click Count.

AC3: GET /api/urls/{short_code}/stats → 200 with short_code, long_url, clicks, created_at,
     expires_at. Non-existent → 404. Clicks reflect actual redirect count.
"""

import httpx

from verify.acceptance.conftest import assert_201, assert_404, assert_json_200


def _create_url(client: httpx.Client, long_url: str, **kwargs) -> dict:
    """Helper: create a short URL and return the parsed response."""
    payload = {"long_url": long_url, **kwargs}
    return assert_201(client.post("/api/urls", json=payload))


def test_stats_returns_url_metadata(client: httpx.Client):
    """Stats for an existing short code returns full metadata."""
    url_obj = _create_url(client, "https://example.com/stats-test")
    short_code = url_obj["short_code"]

    stats = assert_json_200(client.get(f"/api/urls/{short_code}/stats"))

    assert stats["short_code"] == short_code
    assert stats["long_url"] == "https://example.com/stats-test"
    assert "clicks" in stats
    assert "created_at" in stats
    assert "expires_at" in stats


def test_stats_clicks_match_redirect_count(client: httpx.Client):
    """Clicks in stats reflect the number of redirects."""
    url_obj = _create_url(client, "https://example.com/stats-clicks")
    short_code = url_obj["short_code"]

    # Do 5 redirects
    for _ in range(5):
        r = client.get(f"/{short_code}")
        assert r.status_code == 301

    stats = assert_json_200(client.get(f"/api/urls/{short_code}/stats"))
    assert stats["clicks"] == 5, f"Expected 5 clicks after 5 redirects, got {stats['clicks']}"


def test_stats_zero_clicks_after_create(client: httpx.Client):
    """A newly created URL has 0 clicks."""
    url_obj = _create_url(client, "https://example.com/zero-clicks")
    short_code = url_obj["short_code"]

    stats = assert_json_200(client.get(f"/api/urls/{short_code}/stats"))
    assert stats["clicks"] == 0


def test_stats_nonexistent_code_404(client: httpx.Client):
    """Stats for a nonexistent short code → 404."""
    assert_404(client.get("/api/urls/nonexistent99/stats"))
