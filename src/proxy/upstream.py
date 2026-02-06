"""Upstream client for forwarding requests to real registries."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

import aiohttp

from .request_parser import RegistryType
from .cache import ResponseCache

logger = logging.getLogger(__name__)


class UpstreamClient:
    """Client for forwarding requests to upstream registries."""

    # Default upstream registry URLs
    DEFAULT_UPSTREAMS = {
        RegistryType.NPM: "https://registry.npmjs.org",
        RegistryType.PYPI: "https://pypi.org",
        RegistryType.MAVEN: "https://repo1.maven.org/maven2",
        RegistryType.NUGET: "https://api.nuget.org",
    }

    def __init__(
        self,
        upstreams: Optional[Dict[RegistryType, str]] = None,
        timeout: int = 30,
        response_cache: Optional[ResponseCache] = None,
    ):
        """Initialize the upstream client.

        Args:
            upstreams: Override upstream URLs by registry type.
            timeout: Request timeout in seconds.
            response_cache: Optional response cache.
        """
        self._upstreams = {**self.DEFAULT_UPSTREAMS}
        if upstreams:
            self._upstreams.update(upstreams)
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._response_cache = response_cache
        self._session: Optional[aiohttp.ClientSession] = None

    def set_upstream(self, registry_type: RegistryType, url: str) -> None:
        """Set upstream URL for a registry type.

        Args:
            registry_type: Registry type.
            url: Upstream URL.
        """
        self._upstreams[registry_type] = url.rstrip("/")

    def get_upstream(self, registry_type: RegistryType) -> str:
        """Get upstream URL for a registry type.

        Args:
            registry_type: Registry type.

        Returns:
            Upstream URL.
        """
        return self._upstreams.get(registry_type, self.DEFAULT_UPSTREAMS.get(registry_type, ""))

    async def start(self) -> None:
        """Start the HTTP session."""
        if self._session is None:
            connector = aiohttp.TCPConnector(limit=100)
            self._session = aiohttp.ClientSession(
                timeout=self._timeout,
                connector=connector,
                auto_decompress=False,
            )

    async def stop(self) -> None:
        """Stop the HTTP session."""
        if self._session:
            await self._session.close()
            self._session = None

    async def forward(
        self,
        registry_type: RegistryType,
        path: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        body: Optional[bytes] = None,
        use_cache: bool = True,
    ) -> Tuple[int, Dict[str, str], bytes]:
        """Forward a request to the upstream registry.

        Args:
            registry_type: Registry type.
            path: Request path.
            method: HTTP method.
            headers: Optional request headers.
            body: Optional request body.
            use_cache: Whether to use response cache for GET requests.

        Returns:
            Tuple of (status code, response headers, response body).
        """
        upstream_base = self.get_upstream(registry_type)
        if not upstream_base:
            return 502, {}, b'{"error": "No upstream configured for registry type"}'

        url = self._build_url(registry_type, upstream_base, path)

        # Check cache for GET requests
        if method == "GET" and use_cache and self._response_cache:
            cached = self._response_cache.get(url)
            if cached:
                logger.debug("Cache hit for %s", url)
                body, headers = cached
                return 200, headers, body

        # Ensure session is started
        if self._session is None:
            await self.start()

        # Prepare headers
        request_headers = self._build_request_headers(headers)

        try:
            assert self._session is not None
            async with self._session.request(
                method,
                url,
                headers=request_headers,
                data=body,
                allow_redirects=True,
            ) as response:
                response_body = await response.read()
                response_headers = dict(response.headers)

                # Filter response headers
                filtered_headers = self._filter_response_headers(response_headers)

                # Cache successful GET responses
                if method == "GET" and response.status == 200 and use_cache and self._response_cache:
                    self._response_cache.set(url, response_body, filtered_headers)

                return response.status, filtered_headers, response_body

        except aiohttp.ClientError as e:
            logger.error("Upstream request failed: %s", e)
            return 502, {}, b'{"error": "Upstream request failed"}'
        except Exception as e:
            logger.exception("Unexpected error forwarding request: %s", e)
            return 500, {}, b'{"error": "Internal proxy error"}'

    def _build_url(self, registry_type: RegistryType, upstream_base: str, path: str) -> str:
        """Build the upstream URL from base and path."""
        base = upstream_base.rstrip("/")
        request_path = path if path.startswith("/") else f"/{path}"

        # Avoid double /maven2 when clients include it in the path.
        if registry_type == RegistryType.MAVEN:
            maven_prefix = "/maven2"
            if base.endswith(maven_prefix) and request_path.startswith(maven_prefix):
                request_path = request_path[len(maven_prefix):] or "/"

        if not request_path.startswith("/"):
            request_path = f"/{request_path}"

        return f"{base}{request_path}"

    def _build_request_headers(
        self, headers: Optional[Dict[str, str]]
    ) -> Dict[str, str]:
        """Build request headers to send upstream."""
        request_headers: Dict[str, str] = {}
        hop_by_hop = {
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailer",
            "transfer-encoding",
            "upgrade",
            "host",
        }

        connection_tokens = set()
        if headers:
            for k, v in headers.items():
                if k.lower() == "connection":
                    connection_tokens = {token.strip().lower() for token in v.split(",")}
                    break

        if headers:
            for key, value in headers.items():
                key_lower = key.lower()
                if key_lower in hop_by_hop or key_lower in connection_tokens:
                    continue
                request_headers[key] = value

        # Ensure defaults if caller didn't provide them.
        request_headers.setdefault("User-Agent", "DepGate-Proxy/1.0")
        request_headers.setdefault("Accept", "*/*")

        return request_headers

    def _filter_response_headers(self, headers: Dict[str, Any]) -> Dict[str, str]:
        """Filter response headers to forward to client.

        Args:
            headers: Raw response headers.

        Returns:
            Filtered headers dict.
        """
        # Headers to forward
        forward_headers = [
            "Content-Type",
            "Content-Length",
            "ETag",
            "Last-Modified",
            "Cache-Control",
            "Content-Encoding",
        ]

        filtered = {}
        for key, value in headers.items():
            if key in forward_headers:
                filtered[key] = str(value)

        return filtered

    async def __aenter__(self) -> "UpstreamClient":
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.stop()
