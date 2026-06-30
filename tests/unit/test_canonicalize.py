"""Unit tests for URL canonicalization — pure function, no external dependencies."""

import pytest

from src.bitly.services.url_service import canonicalize_url


class TestCanonicalizeUrl:
    def test_lowercases_scheme_and_host(self) -> None:
        result = canonicalize_url("HTTPS://EXAMPLE.COM/path")
        assert result == "https://example.com/path"

    def test_strips_default_https_port_443(self) -> None:
        result = canonicalize_url("https://example.com:443/path?q=1")
        assert result == "https://example.com/path?q=1"

    def test_strips_default_http_port_80(self) -> None:
        result = canonicalize_url("http://example.com:80/page")
        assert result == "http://example.com/page"

    def test_strips_fragment(self) -> None:
        result = canonicalize_url("https://example.com/page#section")
        assert result == "https://example.com/page"

    def test_preserves_query_string(self) -> None:
        result = canonicalize_url("http://example.com/search?q=hello&page=1")
        assert result == "http://example.com/search?q=hello&page=1"

    def test_preserves_non_default_port(self) -> None:
        result = canonicalize_url("http://example.com:8080/api")
        assert result == "http://example.com:8080/api"

    def test_preserves_path(self) -> None:
        result = canonicalize_url("https://example.com/very/long/path")
        assert result == "https://example.com/very/long/path"

    def test_combined_transformations(self) -> None:
        # All transformations in one: lowercase, strip port, strip fragment
        result = canonicalize_url("HTTPS://EXAMPLE.COM:443/path?q=1#section")
        assert result == "https://example.com/path?q=1"

    def test_strips_trailing_whitespace(self) -> None:
        result = canonicalize_url("  https://example.com  ")
        assert result == "https://example.com/"

    # --- Error cases ---

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="long_url is required"):
            canonicalize_url("")

    def test_whitespace_only_raises(self) -> None:
        with pytest.raises(ValueError, match="long_url is required"):
            canonicalize_url("   ")

    def test_no_scheme_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid URL format"):
            canonicalize_url("example.com/path")

    def test_garbage_raises(self) -> None:
        with pytest.raises(ValueError, match="Invalid URL format"):
            canonicalize_url("not-a-url")
