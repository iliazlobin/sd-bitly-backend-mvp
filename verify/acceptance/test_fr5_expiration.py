"""FR5 — URL Expiration.

AC5: POST /api/urls with expires_at → stored. Redirect with expires_at < now() → 410 Gone.
     Stats shows expires_at value. Non-expired links redirect normally.
"""
from datetime import datetime, timedelta, timezone

import httpx

from verify.acceptance.conftest import (
    assert_201,
    assert_301,
    assert_404,
    assert_410,
    assert_json_200,
)


def _create_url(client: httpx.Client, long_url: str, **kwargs) -> dict:
    """Helper: create a short URL and return the parsed response."""
    payload = {"long_url": long_url, **kwargs}
    return assert_201(client.post("/api/urls", json=payload))


def test_create_with_expires_at(client: httpx.Client):
    """Creating with expires_at → 201, expires_at is stored."""
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    body = _create_url(client, "https://example.com/expiring", expires_at=future)
    assert body["expires_at"] is not None


def test_expired_link_returns_410(client: httpx.Client):
    """Redirect to an expired link → 410 Gone."""
    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    url_obj = assert_201(client.post("/api/urls", json={
        "long_url": "https://example.com/already-expired",
        "expires_at": past,
    }))
    short_code = url_obj["short_code"]

    body = assert_410(client.get(f"/{short_code}"))
    assert "detail" in body


def test_stats_shows_expires_at(client: httpx.Client):
    """Stats for an expiring link shows the expires_at value."""
    future = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    url_obj = _create_url(client, "https://example.com/will-expire", expires_at=future)
    short_code = url_obj["short_code"]

    stats = assert_json_200(client.get(f"/api/urls/{short_code}/stats"))
    assert stats["expires_at"] is not None


def test_stats_without_expiry_has_null(client: httpx.Client):
    """Stats for a permanent link has null expires_at."""
    url_obj = _create_url(client, "https://example.com/permanent")
    short_code = url_obj["short_code"]

    stats = assert_json_200(client.get(f"/api/urls/{short_code}/stats"))
    assert stats["expires_at"] is None


def test_non_expired_link_redirects(client: httpx.Client):
    """A link with a future expires_at redirects normally."""
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    url_obj = _create_url(client, "https://example.com/still-alive", expires_at=future)
    short_code = url_obj["short_code"]

    r = assert_301(client.get(f"/{short_code}"))
    assert r.headers["Location"] == "https://example.com/still-alive"


def test_expired_link_stats_still_accessible(client: httpx.Client):
    """Stats remain accessible even after a link expires."""
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    url_obj = assert_201(client.post("/api/urls", json={
        "long_url": "https://example.com/expired-but-stats",
        "expires_at": past,
    }))
    short_code = url_obj["short_code"]

    # Redirect returns 410
    assert_410(client.get(f"/{short_code}"))

    # Stats still work
    stats = assert_json_200(client.get(f"/api/urls/{short_code}/stats"))
    assert stats["short_code"] == short_code
    assert stats["expires_at"] is not None


def test_expired_link_not_found_for_nonexistent(client: httpx.Client):
    """A nonexistent code still returns 404, not 410."""
    assert_404(client.get("/expiredButNotReal"))
