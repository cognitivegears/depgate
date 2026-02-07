"""Tests for the proxy server."""

import json
import pytest
import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Optional
from unittest.mock import MagicMock, patch

# Check if aiohttp is available
aiohttp_mod = pytest.importorskip("aiohttp")

from aiohttp import web
from yarl import URL

from src.proxy.server import RegistryProxyServer, ProxyConfig
from src.proxy.request_parser import RegistryType
from src.analysis.policy import PolicyDecision


class _DummyContent:
    """Async iterable for streamed response content."""

    def __init__(self, body: bytes):
        self._body = body

    async def iter_chunked(self, size: int):
        yield self._body

    async def read(self, n: int = -1) -> bytes:
        return self._body


class _DummyResponse:
    """Minimal async response stub."""

    def __init__(self, status: int = 200, headers: Optional[Dict[str, str]] = None, body: bytes = b"ok"):
        self.status = status
        self.headers = headers or {}
        self._body = body
        self.content = _DummyContent(body)

    async def read(self) -> bytes:
        return self._body


class TestProxyConfig:
    """Tests for ProxyConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ProxyConfig()
        assert config.host == "127.0.0.1"
        assert config.port == 8080
        assert config.decision_mode == "block"
        assert config.cache_ttl == 3600

    def test_config_from_args(self):
        """Test configuration from CLI arguments."""
        args = MagicMock()
        args.PROXY_HOST = "0.0.0.0"
        args.PROXY_PORT = 9000
        args.PROXY_DECISION_MODE = "warn"
        args.PROXY_CACHE_TTL = 7200
        args.PROXY_TIMEOUT = 60
        args.PROXY_UPSTREAM_NPM = "https://custom.npm.registry"
        args.PROXY_UPSTREAM_PYPI = None
        args.PROXY_UPSTREAM_MAVEN = None
        args.PROXY_UPSTREAM_NUGET = None

        config = ProxyConfig.from_args(args)

        assert config.host == "0.0.0.0"
        assert config.port == 9000
        assert config.decision_mode == "warn"
        assert config.cache_ttl == 7200
        assert config.upstream_npm == "https://custom.npm.registry"


class TestProxyServerBasic:
    """Basic tests for the proxy server."""

    def setup_method(self):
        """Set up test fixtures."""
        from metapackage import MetaPackage
        MetaPackage.instances.clear()

    def test_server_initialization(self):
        """Test server initialization."""
        config = ProxyConfig()
        server = RegistryProxyServer(config)
        assert server._config == config
        assert server._decision_cache is not None
        assert server._response_cache is not None

    def test_set_policy_config(self):
        """Test setting policy configuration."""
        config = ProxyConfig()
        server = RegistryProxyServer(config)

        new_policy = {"rules": [{"type": "regex", "target": "package_name", "exclude": ["bad"]}]}
        server.set_policy_config(new_policy)

        assert server._config.policy_config == new_policy

    def test_set_decision_mode(self):
        """Test setting decision mode."""
        config = ProxyConfig()
        server = RegistryProxyServer(config)

        server.set_decision_mode("audit")
        assert server._config.decision_mode == "audit"

    def test_cache_stats(self):
        """Test getting cache statistics."""
        config = ProxyConfig()
        server = RegistryProxyServer(config)

        stats = server.cache_stats()
        assert "decision_cache" in stats
        assert "response_cache" in stats
        assert "total_entries" in stats["decision_cache"]


class TestProxyServerDenyResponse:
    """Tests for deny response generation."""

    def setup_method(self):
        """Set up test fixtures."""
        from metapackage import MetaPackage
        MetaPackage.instances.clear()

    def test_deny_response_format(self):
        """Test deny response has correct format."""
        from src.proxy.request_parser import ParsedRequest
        from src.proxy.evaluator import ProxyEvaluator
        from src.analysis.policy import PolicyDecision

        config = ProxyConfig()
        server = RegistryProxyServer(config)

        parsed = ParsedRequest(
            registry_type=RegistryType.NPM,
            package_name="bad-package",
            version="1.0.0",
            is_metadata_request=True,
            raw_path="/bad-package",
        )

        decision = PolicyDecision(
            decision="deny",
            violated_rules=["excluded by pattern: bad"],
            evaluated_metrics={},
        )

        response = server._deny_response(parsed, decision)

        assert response.status == 403
        assert response.content_type == "application/json"

        body = json.loads(response.body)
        assert body["error"] == "Package blocked by policy"
        assert body["package"] == "bad-package"
        assert body["version"] == "1.0.0"
        assert "violated_rules" in body


class TestProxyServerRegistryDetection:
    """Tests for registry type detection."""

    def setup_method(self):
        """Set up test fixtures."""
        from metapackage import MetaPackage
        MetaPackage.instances.clear()

    def test_detect_npm_from_user_agent(self):
        """Test detecting NPM from User-Agent."""
        config = ProxyConfig()
        server = RegistryProxyServer(config)

        request = MagicMock()
        request.headers = {"User-Agent": "npm/8.19.2 node/v18.12.1"}
        request.path = "/lodash"

        result = server._detect_registry_hint(request)
        assert result == RegistryType.NPM

    def test_detect_pypi_from_user_agent(self):
        """Test detecting PyPI from User-Agent."""
        config = ProxyConfig()
        server = RegistryProxyServer(config)

        request = MagicMock()
        request.headers = {"User-Agent": "pip/23.0.1"}
        request.path = "/simple/requests/"

        result = server._detect_registry_hint(request)
        assert result == RegistryType.PYPI

    def test_detect_maven_from_user_agent(self):
        """Test detecting Maven from User-Agent."""
        config = ProxyConfig()
        server = RegistryProxyServer(config)

        request = MagicMock()
        request.headers = {"User-Agent": "Apache-Maven/3.9.0"}
        request.path = "/maven2/org/apache/commons/commons-lang3/maven-metadata.xml"

        result = server._detect_registry_hint(request)
        assert result == RegistryType.MAVEN

    def test_detect_nuget_from_user_agent(self):
        """Test detecting NuGet from User-Agent."""
        config = ProxyConfig()
        server = RegistryProxyServer(config)

        request = MagicMock()
        request.headers = {"User-Agent": "NuGet Command Line/6.4.0"}
        request.path = "/v3/index.json"

        result = server._detect_registry_hint(request)
        assert result == RegistryType.NUGET

    def test_detect_nuget_from_v3_index_path(self):
        """Test detecting NuGet from /v3/index.json path."""
        config = ProxyConfig()
        server = RegistryProxyServer(config)

        request = MagicMock()
        request.headers = {"User-Agent": "custom-client"}
        request.path = "/v3/index.json"

        result = server._detect_registry_hint(request)
        assert result == RegistryType.NUGET

    def test_detect_nuget_from_flatcontainer_path(self):
        """Test detecting NuGet from /v3-flatcontainer path."""
        config = ProxyConfig()
        server = RegistryProxyServer(config)

        request = MagicMock()
        request.headers = {"User-Agent": "custom-client"}
        request.path = "/v3-flatcontainer/newtonsoft.json/index.json"

        result = server._detect_registry_hint(request)
        assert result == RegistryType.NUGET

    def test_detect_pypi_from_path(self):
        """Test detecting PyPI from path pattern."""
        config = ProxyConfig()
        server = RegistryProxyServer(config)

        request = MagicMock()
        request.headers = {"User-Agent": "custom-client"}
        request.path = "/simple/requests/"

        result = server._detect_registry_hint(request)
        assert result == RegistryType.PYPI

    def test_detect_unknown(self):
        """Test unknown registry detection."""
        config = ProxyConfig()
        server = RegistryProxyServer(config)

        request = MagicMock()
        request.headers = {"User-Agent": "custom-client"}
        request.path = "/some/random/path"

        result = server._detect_registry_hint(request)
        assert result is None


class TestProxyServerCacheIntegration:
    """Tests for cache integration."""

    def setup_method(self):
        """Set up test fixtures."""
        from metapackage import MetaPackage
        MetaPackage.instances.clear()

    def test_decision_cache_populated(self):
        """Test that decisions are cached when policy is configured."""
        config = ProxyConfig()
        # Add a policy config so caching is enabled
        config.policy_config = {
            "rules": [{
                "type": "regex",
                "target": "package_name",
                "include": ["lodash"]
            }]
        }
        server = RegistryProxyServer(config)

        # Simulate evaluation
        decision = server._evaluator.evaluate("lodash", "4.17.21", RegistryType.NPM)

        # Check cache
        cached = server._decision_cache.get("npm", "lodash", "4.17.21")
        assert cached is not None
        assert cached["decision"] == decision.decision


class TestProxyServerAsync:
    """Async tests for the proxy server."""

    def setup_method(self):
        """Set up test fixtures."""
        from metapackage import MetaPackage
        MetaPackage.instances.clear()

    def test_server_has_required_methods(self):
        """Test server has required async methods."""
        config = ProxyConfig(port=0)  # Use port 0 to get random available port
        server = RegistryProxyServer(config)

        # Verify the methods exist
        assert hasattr(server, "start")
        assert hasattr(server, "stop")
        assert hasattr(server, "run_forever")
        assert callable(server.start)
        assert callable(server.stop)
        assert callable(server.run_forever)

    def test_upstream_client_configured(self):
        """Test upstream client is properly configured."""
        config = ProxyConfig()
        config.upstream_npm = "https://custom.registry.com"
        server = RegistryProxyServer(config)

        # Check upstream configuration
        assert server._upstream.get_upstream(RegistryType.NPM) == "https://custom.registry.com"
        assert server._upstream.get_upstream(RegistryType.PYPI) == config.upstream_pypi

    def test_forward_preserves_query_string(self):
        """Test that query strings are forwarded to upstream."""
        config = ProxyConfig()
        server = RegistryProxyServer(config)
        seen = {}

        @asynccontextmanager
        async def _open_response(url, method, headers, body):
            seen["url"] = url
            yield _DummyResponse(
                status=200,
                headers={"Content-Length": "2", "Content-Type": "text/plain"},
                body=b"ok",
            )

        server._upstream.open_response = _open_response

        request = MagicMock()
        request.rel_url = URL("/-/v1/search?text=lodash&size=20")
        request.path = "/-/v1/search"
        request.method = "GET"
        request.headers = {}
        request.body_exists = False

        response = asyncio.run(server._handle_request(request))

        assert isinstance(response, web.Response)
        assert seen["url"].endswith("/-/v1/search?text=lodash&size=20")

    def test_unknown_registry_type_returns_400(self):
        """Test that parsed requests with UNKNOWN registry type return 400."""
        from src.proxy.request_parser import ParsedRequest

        config = ProxyConfig()
        server = RegistryProxyServer(config)

        # Mock the parser to return UNKNOWN registry type with a package name
        server._parser.parse = MagicMock(return_value=ParsedRequest(
            registry_type=RegistryType.UNKNOWN,
            package_name="some-package",
            version="1.0.0",
            is_metadata_request=True,
            raw_path="/some-package",
        ))

        request = MagicMock()
        request.rel_url = URL("/some-package")
        request.path = "/some-package"
        request.method = "GET"
        request.headers = {"User-Agent": "custom-client"}
        request.body_exists = False

        response = asyncio.run(server._handle_request(request))

        assert response.status == 400
        body = json.loads(response.body)
        assert "Could not determine registry type" in body["error"]


class TestProxyServerHealthCheck:
    """Tests for health check endpoint."""

    def setup_method(self):
        """Set up test fixtures."""
        from metapackage import MetaPackage
        MetaPackage.instances.clear()

    def test_health_check_endpoint(self):
        """Test health check returns 200 with status ok."""
        import aiohttp
        import aiohttp.test_utils

        async def _run():
            config = ProxyConfig(port=0)
            server = RegistryProxyServer(config)
            app = server._create_app()
            async with aiohttp.test_utils.TestServer(app) as ts:
                async with aiohttp.ClientSession() as session:
                    resp = await session.get(
                        f"http://{ts.host}:{ts.port}/_depgate/health"
                    )
                    assert resp.status == 200
                    data = await resp.json()
                    assert data["status"] == "ok"
                    assert "decision_mode" in data
                    assert "cache" in data

        asyncio.run(_run())


class TestResponseCacheByteTracking:
    """Tests for response cache byte tracking correctness."""

    def test_byte_tracking_add_remove(self):
        """Test that byte tracking stays accurate across add/remove cycles."""
        from src.proxy.cache import ResponseCache

        cache = ResponseCache(default_ttl=300)

        cache.set("http://a.com/1", b"hello", {"Content-Type": "text/plain"})
        assert cache._current_bytes == 5

        cache.set("http://a.com/2", b"world!", {"Content-Type": "text/plain"})
        assert cache._current_bytes == 11

        cache.invalidate("http://a.com/1")
        assert cache._current_bytes == 6

        cache.clear()
        assert cache._current_bytes == 0

    def test_byte_tracking_no_negative_drift(self):
        """Test that byte tracking never goes negative."""
        from src.proxy.cache import ResponseCache

        cache = ResponseCache(default_ttl=300)

        # Force _current_bytes to 0 and remove a non-existent entry
        cache._current_bytes = 0
        cache._remove_entry("http://nonexistent.com")
        assert cache._current_bytes == 0


class TestProxyServerRegistryIntegration:
    """Integration-style tests for registry handling."""

    def _run_request(self, path: str, user_agent: str, expected_registry, expected_pkg, expected_version):
        config = ProxyConfig()
        server = RegistryProxyServer(config)

        server._evaluator.evaluate = MagicMock(
            return_value=PolicyDecision("allow", [], {})
        )

        @asynccontextmanager
        async def _open_response(url, method, headers, body):
            yield _DummyResponse(
                status=200,
                headers={"Content-Length": "2", "Content-Type": "text/plain"},
                body=b"ok",
            )

        server._upstream.open_response = _open_response

        request = MagicMock()
        request.rel_url = URL(path)
        request.path = URL(path).path
        request.method = "GET"
        request.headers = {"User-Agent": user_agent}
        request.body_exists = False

        response = asyncio.run(server._handle_request(request))

        assert isinstance(response, web.Response)
        server._evaluator.evaluate.assert_called_once_with(
            expected_pkg, expected_version, expected_registry
        )

    def test_integration_npm(self):
        """NPM metadata request is evaluated and forwarded."""
        self._run_request(
            "/lodash",
            "npm/9.0.0",
            RegistryType.NPM,
            "lodash",
            None,
        )

    def test_integration_pypi(self):
        """PyPI simple index request is evaluated and forwarded."""
        self._run_request(
            "/simple/requests/",
            "pip/23.0.1",
            RegistryType.PYPI,
            "requests",
            None,
        )

    def test_integration_maven(self):
        """Maven artifact request is evaluated and forwarded."""
        self._run_request(
            "/maven2/org/apache/commons/commons-lang3/3.12.0/commons-lang3-3.12.0.jar",
            "Apache-Maven/3.9.0",
            RegistryType.MAVEN,
            "org.apache.commons:commons-lang3",
            "3.12.0",
        )

    def test_integration_nuget(self):
        """NuGet registration request is evaluated and forwarded."""
        self._run_request(
            "/v3/registration5-gz-semver2/newtonsoft.json/index.json",
            "NuGet Command Line/6.4.0",
            RegistryType.NUGET,
            "newtonsoft.json",
            None,
        )


class TestProxyServerStreaming:
    """Tests for streaming and cache behaviour in _forward_request."""

    def setup_method(self):
        from metapackage import MetaPackage
        MetaPackage.instances.clear()

    def _make_server(self):
        config = ProxyConfig()
        return RegistryProxyServer(config)

    def _make_request(self, path="/lodash", method="GET", user_agent="npm/9.0.0"):
        request = MagicMock()
        request.rel_url = URL(path)
        request.path = URL(path).path
        request.method = method
        request.headers = {"User-Agent": user_agent}
        request.body_exists = False
        return request

    # -- Test 5: streaming for known-large responses --

    def test_large_response_streams_and_skips_cache(self):
        """Responses larger than max_entry_bytes are streamed, not cached."""
        server = self._make_server()
        max_bytes = server._response_cache.max_entry_bytes()
        large_body = b"x" * (max_bytes + 1)

        @asynccontextmanager
        async def _open_response(url, method, headers, body):
            yield _DummyResponse(
                status=200,
                headers={
                    "Content-Length": str(len(large_body)),
                    "Content-Type": "application/octet-stream",
                },
                body=large_body,
            )

        server._upstream.open_response = _open_response

        written = []

        async def _run():
            mock_stream = MagicMock()
            mock_stream.status = 200
            mock_stream.headers = {}

            async def _prepare(req):
                pass

            async def _write(chunk):
                written.append(chunk)

            async def _write_eof():
                pass

            mock_stream.prepare = _prepare
            mock_stream.write = _write
            mock_stream.write_eof = _write_eof

            with patch.object(web, "StreamResponse", return_value=mock_stream):
                return await server._handle_request(self._make_request())

        asyncio.run(_run())

        assert b"".join(written) == large_body
        # Verify not cached
        cache_key = server._upstream.cache_key(
            server._upstream.build_request(RegistryType.NPM, "/lodash", {"User-Agent": "npm/9.0.0"})[0],
            server._upstream.build_request(RegistryType.NPM, "/lodash", {"User-Agent": "npm/9.0.0"})[1],
        )
        assert server._response_cache.get(cache_key) is None

    def test_non_cacheable_response_streams(self):
        """Responses with Cache-Control: no-store are streamed."""
        server = self._make_server()

        @asynccontextmanager
        async def _open_response(url, method, headers, body):
            yield _DummyResponse(
                status=200,
                headers={
                    "Content-Length": "5",
                    "Content-Type": "text/plain",
                    "Cache-Control": "no-store",
                },
                body=b"hello",
            )

        server._upstream.open_response = _open_response
        written = []

        async def _run():
            mock_stream = MagicMock()

            async def _prepare(req):
                pass

            async def _write(chunk):
                written.append(chunk)

            async def _write_eof():
                pass

            mock_stream.prepare = _prepare
            mock_stream.write = _write
            mock_stream.write_eof = _write_eof

            with patch.object(web, "StreamResponse", return_value=mock_stream):
                return await server._handle_request(self._make_request())

        asyncio.run(_run())

        assert b"".join(written) == b"hello"

    # -- Test 6: error handling paths --

    def test_client_error_returns_502(self):
        """aiohttp.ClientError from upstream returns 502."""
        server = self._make_server()

        @asynccontextmanager
        async def _open_response(url, method, headers, body):
            raise aiohttp_mod.ClientError("connection refused")
            yield  # pragma: no cover – unreachable, needed for generator

        server._upstream.open_response = _open_response

        response = asyncio.run(
            server._handle_request(self._make_request())
        )

        assert response.status == 502
        body = json.loads(response.body)
        assert body["error"] == "Upstream request failed"

    def test_unexpected_error_returns_500(self):
        """Unexpected exceptions from upstream return 500."""
        server = self._make_server()

        @asynccontextmanager
        async def _open_response(url, method, headers, body):
            raise RuntimeError("something broke")
            yield  # pragma: no cover

        server._upstream.open_response = _open_response

        response = asyncio.run(
            server._handle_request(self._make_request())
        )

        assert response.status == 500
        body = json.loads(response.body)
        assert body["error"] == "Internal proxy error"

    # -- Test 7: cache miss → cache set flow --

    def test_cacheable_response_is_cached(self):
        """Small cacheable GET responses are stored in the response cache."""
        server = self._make_server()

        @asynccontextmanager
        async def _open_response(url, method, headers, body):
            yield _DummyResponse(
                status=200,
                headers={"Content-Length": "11", "Content-Type": "application/json"},
                body=b'{"ok":true}',
            )

        server._upstream.open_response = _open_response

        request = self._make_request()
        response = asyncio.run(server._handle_request(request))

        assert isinstance(response, web.Response)
        assert response.body == b'{"ok":true}'

        # Verify it was cached — second request should hit the cache
        # without open_response being called
        called = {"count": 0}

        @asynccontextmanager
        async def _should_not_call(url, method, headers, body):
            called["count"] += 1
            yield _DummyResponse()  # pragma: no cover

        server._upstream.open_response = _should_not_call

        request2 = self._make_request()
        response2 = asyncio.run(server._handle_request(request2))

        assert response2.status == 200
        assert response2.body == b'{"ok":true}'
        assert called["count"] == 0

    # -- Test 8: missing Content-Length --

    def test_chunked_response_cached_when_small(self):
        """Responses without Content-Length are buffered and cached if small."""
        server = self._make_server()

        @asynccontextmanager
        async def _open_response(url, method, headers, body):
            yield _DummyResponse(
                status=200,
                headers={"Content-Type": "application/json"},  # no Content-Length
                body=b'{"chunked":true}',
            )

        server._upstream.open_response = _open_response

        response = asyncio.run(
            server._handle_request(self._make_request())
        )

        assert isinstance(response, web.Response)
        assert response.body == b'{"chunked":true}'

        # Confirm it was cached
        called = {"count": 0}

        @asynccontextmanager
        async def _should_not_call(url, method, headers, body):
            called["count"] += 1
            yield _DummyResponse()  # pragma: no cover

        server._upstream.open_response = _should_not_call

        response2 = asyncio.run(
            server._handle_request(self._make_request())
        )
        assert response2.body == b'{"chunked":true}'
        assert called["count"] == 0

    def test_chunked_large_response_not_cached(self):
        """Large responses without Content-Length are returned but not cached."""
        server = self._make_server()
        max_bytes = server._response_cache.max_entry_bytes()
        large_body = b"y" * (max_bytes + 1)

        @asynccontextmanager
        async def _open_response(url, method, headers, body):
            yield _DummyResponse(
                status=200,
                headers={"Content-Type": "application/octet-stream"},
                body=large_body,
            )

        server._upstream.open_response = _open_response

        response = asyncio.run(
            server._handle_request(self._make_request())
        )

        assert isinstance(response, web.Response)
        assert response.body == large_body

        # Verify not cached — next request should call upstream again
        called = {"count": 0}

        @asynccontextmanager
        async def _counting_open(url, method, headers, body):
            called["count"] += 1
            yield _DummyResponse(
                status=200,
                headers={"Content-Type": "application/octet-stream"},
                body=large_body,
            )

        server._upstream.open_response = _counting_open

        asyncio.run(server._handle_request(self._make_request()))
        assert called["count"] == 1
