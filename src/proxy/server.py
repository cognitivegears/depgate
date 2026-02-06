"""Registry proxy server using aiohttp."""

from __future__ import annotations

import asyncio
import json
import logging
import signal
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from aiohttp import web

from .request_parser import RequestParser, ParsedRequest, RegistryType
from .upstream import UpstreamClient
from .evaluator import ProxyEvaluator
from .cache import DecisionCache, ResponseCache

logger = logging.getLogger(__name__)


@dataclass
class ProxyConfig:
    """Configuration for the proxy server."""

    host: str = "127.0.0.1"
    port: int = 8080
    upstream_npm: str = "https://registry.npmjs.org"
    upstream_pypi: str = "https://pypi.org"
    upstream_maven: str = "https://repo1.maven.org/maven2"
    upstream_nuget: str = "https://api.nuget.org"
    policy_config: Dict[str, Any] = field(default_factory=dict)
    decision_mode: str = "block"
    cache_ttl: int = 3600
    response_cache_ttl: int = 300
    timeout: int = 30

    @classmethod
    def from_args(cls, args: Any) -> "ProxyConfig":
        """Create config from CLI arguments.

        Args:
            args: Parsed CLI arguments namespace.

        Returns:
            ProxyConfig instance.
        """
        config = cls(
            host=getattr(args, "PROXY_HOST", "127.0.0.1"),
            port=getattr(args, "PROXY_PORT", 8080),
            decision_mode=getattr(args, "PROXY_DECISION_MODE", "block"),
            cache_ttl=getattr(args, "PROXY_CACHE_TTL", 3600),
            response_cache_ttl=getattr(args, "PROXY_RESPONSE_CACHE_TTL", 300),
            timeout=getattr(args, "PROXY_TIMEOUT", 30),
        )

        # Override upstreams if provided
        if getattr(args, "PROXY_UPSTREAM_NPM", None):
            config.upstream_npm = args.PROXY_UPSTREAM_NPM
        if getattr(args, "PROXY_UPSTREAM_PYPI", None):
            config.upstream_pypi = args.PROXY_UPSTREAM_PYPI
        if getattr(args, "PROXY_UPSTREAM_MAVEN", None):
            config.upstream_maven = args.PROXY_UPSTREAM_MAVEN
        if getattr(args, "PROXY_UPSTREAM_NUGET", None):
            config.upstream_nuget = args.PROXY_UPSTREAM_NUGET

        return config


class RegistryProxyServer:
    """HTTP proxy server for package registries.

    Acts as a drop-in replacement for package registries, intercepting
    requests to evaluate packages against policy rules before forwarding
    to the upstream registry.
    """

    def __init__(self, config: ProxyConfig):
        """Initialize the proxy server.

        Args:
            config: Server configuration.
        """
        self._config = config
        self._app: Optional[web.Application] = None
        self._runner: Optional[web.AppRunner] = None

        # Initialize caches
        self._decision_cache = DecisionCache(default_ttl=config.cache_ttl)
        self._response_cache = ResponseCache(default_ttl=config.response_cache_ttl)

        # Initialize request parser
        self._parser = RequestParser()

        # Initialize upstream client
        self._upstream = UpstreamClient(
            upstreams={
                RegistryType.NPM: config.upstream_npm,
                RegistryType.PYPI: config.upstream_pypi,
                RegistryType.MAVEN: config.upstream_maven,
                RegistryType.NUGET: config.upstream_nuget,
            },
            timeout=config.timeout,
            response_cache=self._response_cache,
        )

        # Initialize evaluator
        self._evaluator = ProxyEvaluator(
            policy_config=config.policy_config,
            decision_cache=self._decision_cache,
            decision_mode=config.decision_mode,
        )

    def _create_app(self) -> web.Application:
        """Create the aiohttp application."""
        app = web.Application(client_max_size=10 * 1024 * 1024)  # 10MB body limit
        app.router.add_get("/_depgate/health", self._health_check)
        app.router.add_route("*", "/{path:.*}", self._handle_request)
        app.on_startup.append(self._on_startup)
        app.on_cleanup.append(self._on_cleanup)
        return app

    async def _health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint."""
        return web.json_response({
            "status": "ok",
            "decision_mode": self._config.decision_mode,
            "cache": self.cache_stats(),
        })

    async def _on_startup(self, app: web.Application) -> None:
        """Called when the server starts."""
        await self._upstream.start()
        logger.info("Proxy server starting on %s:%s", self._config.host, self._config.port)

    async def _on_cleanup(self, app: web.Application) -> None:
        """Called when the server stops."""
        await self._upstream.stop()
        logger.info("Proxy server stopped")

    async def _handle_request(self, request: web.Request) -> web.Response:
        """Handle incoming registry requests.

        Args:
            request: Incoming HTTP request.

        Returns:
            HTTP response.
        """
        path = request.rel_url.path
        path_qs = request.rel_url.path_qs
        method = request.method

        # Detect registry type from request headers or path
        registry_hint = self._detect_registry_hint(request)

        # Parse the request
        parsed = self._parser.parse(path, registry_hint)

        if not parsed.package_name:
            # Could not parse package info, pass through to upstream
            logger.debug("Unparseable request, passing through: %s", path)
            return await self._forward_request(request, parsed.registry_type, path_qs)

        if parsed.registry_type == RegistryType.UNKNOWN:
            logger.warning("Could not determine registry type for: %s", path)
            return web.json_response(
                {"error": "Could not determine registry type", "path": path},
                status=400,
            )

        logger.info(
            "Request: %s %s -> %s:%s:%s",
            method, path, parsed.registry_type.value,
            parsed.package_name, parsed.version or "latest",
        )

        # Evaluate policy for metadata and tarball requests
        if parsed.is_metadata_request or parsed.is_tarball_request:
            decision = self._evaluator.evaluate(
                parsed.package_name,
                parsed.version,
                parsed.registry_type,
            )

            if decision.decision == "deny":
                logger.warning(
                    "Blocked: %s:%s:%s - %s",
                    parsed.registry_type.value, parsed.package_name,
                    parsed.version, decision.violated_rules,
                )
                return self._deny_response(parsed, decision)

            # Log violations in warn/audit mode
            if decision.violated_rules:
                logger.info(
                    "Allowed with violations (%s): %s - %s",
                    self._config.decision_mode, parsed.package_name,
                    decision.violated_rules,
                )

        # Forward to upstream
        return await self._forward_request(request, parsed.registry_type, path_qs)

    def _detect_registry_hint(self, request: web.Request) -> Optional[RegistryType]:
        """Detect registry type from request headers.

        Args:
            request: HTTP request.

        Returns:
            Registry type hint or None.
        """
        # Check User-Agent for npm/pip/maven/nuget
        user_agent = request.headers.get("User-Agent", "").lower()
        if "npm" in user_agent or "node" in user_agent:
            return RegistryType.NPM
        if "pip" in user_agent or "python" in user_agent:
            return RegistryType.PYPI
        if "maven" in user_agent or "gradle" in user_agent:
            return RegistryType.MAVEN
        if "nuget" in user_agent or "dotnet" in user_agent:
            return RegistryType.NUGET

        # Check Accept header
        accept = request.headers.get("Accept", "")
        if "application/vnd.npm" in accept:
            return RegistryType.NPM

        # Check path patterns
        path = request.path
        if path.startswith("/simple/") or path.startswith("/pypi/"):
            return RegistryType.PYPI
        if path.startswith("/v3/") or path.startswith("/v3-flatcontainer/"):
            return RegistryType.NUGET
        if "/maven2/" in path or path.endswith(".pom") or path.endswith(".jar"):
            return RegistryType.MAVEN

        return None

    async def _forward_request(
        self,
        request: web.Request,
        registry_type: RegistryType,
        path: str,
    ) -> web.Response:
        """Forward request to upstream registry.

        Args:
            request: Original request.
            registry_type: Registry type.
            path: Request path, including query string if present.

        Returns:
            Response from upstream.
        """
        # Read request body if present
        body = None
        if request.body_exists:
            body = await request.read()

        # Forward to upstream
        status, headers, response_body = await self._upstream.forward(
            registry_type,
            path,
            method=request.method,
            headers=dict(request.headers),
            body=body,
        )

        # Build response
        return web.Response(
            status=status,
            headers=headers,
            body=response_body,
        )

    def _deny_response(
        self,
        parsed: ParsedRequest,
        decision: Any,
    ) -> web.Response:
        """Create a deny response for blocked packages.

        Args:
            parsed: Parsed request info.
            decision: Policy decision.

        Returns:
            403 Forbidden response.
        """
        response_body = {
            "error": "Package blocked by policy",
            "package": parsed.package_name,
            "version": parsed.version,
            "registry": parsed.registry_type.value,
            "violated_rules": decision.violated_rules,
            "message": (
                f"Package {parsed.package_name}"
                + (f"@{parsed.version}" if parsed.version else "")
                + " is blocked by depgate policy. "
                + f"Violations: {', '.join(decision.violated_rules)}"
            ),
        }

        return web.Response(
            status=403,
            content_type="application/json",
            body=json.dumps(response_body, indent=2).encode(),
        )

    def set_policy_config(self, config: Dict[str, Any]) -> None:
        """Update the policy configuration.

        Args:
            config: New policy configuration.
        """
        self._config.policy_config = config
        self._evaluator.set_policy_config(config)

    def set_decision_mode(self, mode: str) -> None:
        """Update the decision mode.

        Args:
            mode: New decision mode.
        """
        self._config.decision_mode = mode
        self._evaluator.set_decision_mode(mode)

    def cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict with decision and response cache stats.
        """
        return {
            "decision_cache": self._decision_cache.stats(),
            "response_cache": self._response_cache.stats(),
        }

    async def start(self) -> None:
        """Start the proxy server."""
        self._app = self._create_app()
        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        site = web.TCPSite(
            self._runner,
            self._config.host,
            self._config.port,
        )
        await site.start()

        logger.info(
            "DepGate proxy server listening on http://%s:%s",
            self._config.host, self._config.port,
        )
        logger.info("Decision mode: %s", self._config.decision_mode)
        logger.info("Upstream NPM: %s", self._config.upstream_npm)
        logger.info("Upstream PyPI: %s", self._config.upstream_pypi)
        logger.info("Upstream Maven: %s", self._config.upstream_maven)
        logger.info("Upstream NuGet: %s", self._config.upstream_nuget)

    async def run_forever(self) -> None:
        """Start the server and run until interrupted."""
        await self.start()
        self._stop_event = asyncio.Event()
        try:
            await self._stop_event.wait()
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    async def stop(self) -> None:
        """Stop the proxy server."""
        if hasattr(self, "_stop_event"):
            self._stop_event.set()
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
            self._app = None


def run_proxy_server_sync(config: ProxyConfig) -> None:
    """Run the proxy server synchronously.

    Installs signal handlers for SIGTERM and SIGINT for clean shutdown.

    Args:
        config: Server configuration.
    """
    server = RegistryProxyServer(config)
    loop = asyncio.new_event_loop()

    async def run():
        await server.start()
        stop_event = asyncio.Event()
        running_loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            running_loop.add_signal_handler(sig, stop_event.set)
        await stop_event.wait()
        logger.info("Shutdown signal received, stopping...")
        await server.stop()

    try:
        loop.run_until_complete(run())
    except KeyboardInterrupt:
        # Fallback for platforms where signal handlers don't work (Windows)
        loop.run_until_complete(server.stop())
    finally:
        loop.close()
        logger.info("Proxy server shutdown complete")
