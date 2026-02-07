"""Tests for upstream client helpers."""

from src.proxy.upstream import UpstreamClient
from src.proxy.request_parser import RegistryType


class TestUpstreamClientUrlBuilding:
    """Tests for upstream URL building."""

    def test_maven_base_does_not_double_maven2(self):
        """Ensure /maven2 is not duplicated when already in path."""
        client = UpstreamClient()
        base = "https://repo1.maven.org/maven2"
        path = "/maven2/org/apache/commons/commons-lang3/3.12.0/commons-lang3-3.12.0.jar"

        url = client._build_url(RegistryType.MAVEN, base, path)

        assert url == (
            "https://repo1.maven.org/maven2/"
            "org/apache/commons/commons-lang3/3.12.0/commons-lang3-3.12.0.jar"
        )


class TestUpstreamClientHeaders:
    """Tests for upstream request header handling."""

    def test_build_request_headers_forwards_required_headers(self):
        """Ensure auth/content headers are preserved and hop-by-hop removed."""
        client = UpstreamClient()
        headers = {
            "Authorization": "Bearer token",
            "Content-Type": "application/json",
            "Connection": "keep-alive, X-Custom",
            "X-Custom": "remove-me",
            "Host": "example.com",
        }

        result = client._build_request_headers(headers)

        assert result["Authorization"] == "Bearer token"
        assert result["Content-Type"] == "application/json"
        assert "Connection" not in result
        assert "X-Custom" not in result
        assert "Host" not in result
        assert result["User-Agent"] == "DepGate-Proxy/1.0"
        assert result["Accept"] == "*/*"

    def test_build_request_headers_preserves_accept(self):
        """Ensure provided Accept header is preserved."""
        client = UpstreamClient()
        headers = {
            "Accept": "application/json",
        }

        result = client._build_request_headers(headers)

        assert result["Accept"] == "application/json"

    def test_build_request_headers_case_insensitive_connection(self):
        """Ensure Connection header is matched case-insensitively."""
        client = UpstreamClient()
        headers = {
            "connection": "keep-alive, X-Custom",
            "X-Custom": "remove-me",
            "Accept": "application/json",
        }

        result = client._build_request_headers(headers)

        assert "connection" not in result
        assert "Connection" not in result
        assert "X-Custom" not in result
        assert result["Accept"] == "application/json"


class TestUpstreamClientResponseHeaders:
    """Tests for response header filtering."""

    def test_filter_forwards_known_headers(self):
        """Ensure standard headers are forwarded."""
        client = UpstreamClient()
        headers = {
            "Content-Type": "application/json",
            "Content-Length": "42",
            "ETag": '"abc"',
            "X-Request-Id": "12345",
        }

        result = client.filter_response_headers(headers)

        assert result["Content-Type"] == "application/json"
        assert result["Content-Length"] == "42"
        assert result["ETag"] == '"abc"'
        assert "X-Request-Id" not in result

    def test_filter_case_insensitive_matching(self):
        """Ensure headers with non-canonical casing are matched."""
        client = UpstreamClient()
        headers = {
            "content-type": "text/html",
            "CONTENT-LENGTH": "100",
            "etag": '"xyz"',
            "cache-control": "max-age=300",
        }

        result = client.filter_response_headers(headers)

        assert result["Content-Type"] == "text/html"
        assert result["Content-Length"] == "100"
        assert result["ETag"] == '"xyz"'
        assert result["Cache-Control"] == "max-age=300"

    def test_filter_emits_canonical_casing(self):
        """Ensure output keys use canonical casing regardless of input."""
        client = UpstreamClient()
        headers = {"content-encoding": "gzip", "last-modified": "Thu, 01 Jan 2025"}

        result = client.filter_response_headers(headers)

        assert list(result.keys()) == ["Content-Encoding", "Last-Modified"]

    def test_filter_empty_headers(self):
        """Ensure empty input returns empty output."""
        client = UpstreamClient()
        assert client.filter_response_headers({}) == {}


class TestUpstreamClientCaching:
    """Tests for upstream cache key and cacheability checks."""

    def test_cache_key_varies_on_accept(self):
        """Ensure cache key varies with Accept header."""
        client = UpstreamClient()
        key_a = client.cache_key(
            "https://example.com/pkg",
            {"Accept": "application/json", "Accept-Encoding": "gzip"},
        )
        key_b = client.cache_key(
            "https://example.com/pkg",
            {"Accept": "text/plain", "Accept-Encoding": "gzip"},
        )
        assert key_a != key_b

    def test_cacheable_request_rejects_auth(self):
        """Ensure auth/cookie requests are not cached."""
        client = UpstreamClient()
        assert client.is_cacheable_request({"Authorization": "Bearer token"}) is False
        assert client.is_cacheable_request({"Cookie": "a=b"}) is False

    def test_cacheable_response_rejects_vary_star(self):
        """Ensure responses with Vary:* are not cached."""
        client = UpstreamClient()
        assert client.is_cacheable_response({"Vary": "*"}) is False

    def test_cacheable_response_allows_accept_encoding_vary(self):
        """Ensure Vary: Accept-Encoding is cacheable."""
        client = UpstreamClient()
        assert client.is_cacheable_response({"Vary": "Accept-Encoding"}) is True
