"""Tests for upstream client helpers."""

import asyncio
import pytest

aiohttp_mod = pytest.importorskip("aiohttp")

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
            "Location": "https://example.com/redirect",
            "Content-Range": "bytes 0-41/42",
            "Accept-Ranges": "bytes",
            "X-Request-Id": "12345",
        }

        result = client.filter_response_headers(headers)

        assert result["Content-Type"] == "application/json"
        assert result["Content-Length"] == "42"
        assert result["ETag"] == '"abc"'
        assert result["Location"] == "https://example.com/redirect"
        assert result["Content-Range"] == "bytes 0-41/42"
        assert result["Accept-Ranges"] == "bytes"
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

    def test_cacheable_request_rejects_range(self):
        """Ensure requests with Range header are not cached."""
        client = UpstreamClient()
        assert client.is_cacheable_request({"Range": "bytes=0-1023"}) is False

    def test_cacheable_request_allows_normal(self):
        """Ensure normal requests without auth/cookie/range are cacheable."""
        client = UpstreamClient()
        assert client.is_cacheable_request({"Accept": "application/json"}) is True


class TestUpstreamClientProxyConnection:
    """Tests for Proxy-Connection header stripping."""

    def test_proxy_connection_stripped(self):
        """Ensure Proxy-Connection header is stripped from upstream requests."""
        client = UpstreamClient()
        headers = {
            "Proxy-Connection": "keep-alive",
            "Accept": "application/json",
        }

        result = client._build_request_headers(headers)

        assert "Proxy-Connection" not in result
        assert "proxy-connection" not in result
        assert result["Accept"] == "application/json"


class TestUpstreamClientVaryForwarding:
    """Tests for Vary header forwarding in response."""

    def test_vary_header_forwarded(self):
        """Ensure Vary header is forwarded to clients."""
        client = UpstreamClient()
        headers = {
            "Content-Type": "application/json",
            "Vary": "Accept, Accept-Encoding",
        }

        result = client.filter_response_headers(headers)

        assert result["Vary"] == "Accept, Accept-Encoding"

    def test_vary_header_canonical_casing(self):
        """Ensure Vary is output with canonical casing."""
        client = UpstreamClient()
        headers = {"vary": "Accept"}

        result = client.filter_response_headers(headers)

        assert "Vary" in result
        assert result["Vary"] == "Accept"


class _DummyResponse:
    def __init__(self, status, headers=None, body=b""):
        self.status = status
        self.headers = headers or {}
        self._body = body

    async def read(self):
        return self._body

    def release(self):
        pass


class _DummySession:
    def __init__(self, responses, urls):
        self._responses = iter(responses)
        self._urls = urls

    async def request(self, method, url, headers=None, data=None, allow_redirects=False):
        self._urls.append(url)
        return next(self._responses)


class TestUpstreamClientRedirects:
    def test_follow_allowed_redirect(self):
        """Allowed redirects should be followed for GET requests."""
        client = UpstreamClient()
        urls = []
        client._session = _DummySession(
            [
                _DummyResponse(
                    status=302,
                    headers={"Location": "https://files.pythonhosted.org/packages/x/y/z.whl"},
                ),
                _DummyResponse(
                    status=200,
                    headers={"Content-Type": "text/plain"},
                    body=b"ok",
                ),
            ],
            urls,
        )

        async def _run():
            async with client.open_response(
                "https://pypi.org/simple/requests/",
                method="GET",
                headers={},
                body=None,
            ) as response:
                body = await response.read()
                assert body == b"ok"

        asyncio.run(_run())
        assert urls[0] == "https://pypi.org/simple/requests/"
        assert urls[1].startswith("https://files.pythonhosted.org/")

    def test_block_disallowed_redirect(self):
        """Disallowed redirects should raise ClientError."""
        client = UpstreamClient()
        urls = []
        client._session = _DummySession(
            [
                _DummyResponse(
                    status=302,
                    headers={"Location": "http://169.254.169.254/latest/meta-data"},
                ),
            ],
            urls,
        )

        async def _run():
            async with client.open_response(
                "https://pypi.org/simple/requests/",
                method="GET",
                headers={},
                body=None,
            ):
                pass  # pragma: no cover

        with pytest.raises(aiohttp_mod.ClientError):
            asyncio.run(_run())
