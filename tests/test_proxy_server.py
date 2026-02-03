"""Tests for the proxy server."""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Check if aiohttp is available
pytest.importorskip("aiohttp")

from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop

from src.proxy.server import RegistryProxyServer, ProxyConfig
from src.proxy.request_parser import RegistryType


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
