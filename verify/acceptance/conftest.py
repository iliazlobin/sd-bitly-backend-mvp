"""Shared fixtures and helpers for the Bitly black-box acceptance suite.

These tests do NOT import `src.bitly`. They talk to the running system
via HTTP at API_BASE_URL.
"""

import os

import httpx
import pytest

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="session")
def base_url() -> str:
    return API_BASE_URL


@pytest.fixture(scope="session")
def client(base_url: str) -> httpx.Client:
    """Session-scoped httpx client for the entire acceptance run."""
    with httpx.Client(base_url=base_url, timeout=10) as c:
        yield c


# --- Assert helpers ---------------------------------------------------------


def assert_json_200(r: httpx.Response, expected_status: int = 200):
    """Assert status and return parsed JSON."""
    assert (
        r.status_code == expected_status
    ), f"Expected {expected_status}, got {r.status_code}: {r.text}"
    return r.json()


def assert_201(r: httpx.Response):
    return assert_json_200(r, 201)


def assert_301(r: httpx.Response):
    assert r.status_code == 301, f"Expected 301, got {r.status_code}: {r.text}"
    return r


def assert_404(r: httpx.Response):
    assert r.status_code == 404, f"Expected 404, got {r.status_code}: {r.text}"
    return r.json()


def assert_409(r: httpx.Response):
    assert r.status_code == 409, f"Expected 409, got {r.status_code}: {r.text}"
    return r.json()


def assert_410(r: httpx.Response):
    assert r.status_code == 410, f"Expected 410, got {r.status_code}: {r.text}"
    return r.json()


def assert_422(r: httpx.Response):
    assert r.status_code == 422, f"Expected 422, got {r.status_code}: {r.text}"
    return r.json()


def assert_429(r: httpx.Response):
    assert r.status_code == 429, f"Expected 429, got {r.status_code}: {r.text}"
    assert "Retry-After" in r.headers, "429 must include Retry-After header"
    return r.json()
