"""Upstream client for forwarding requests to real registries."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional, Tuple

import aiohttp

from .request_parser import RegistryType

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
    ):
        """Initialize the upstream client.

        Args:
            upstreams: Override upstream URLs by registry type.
            timeout: Request timeout in seconds.
        """
        self._upstreams = {**self.DEFAULT_UPSTREAMS}
        if upstreams:
            self._upstreams.update(upstreams)
        self._timeout = aiohttp.ClientTimeout(total=timeout)
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

    def build_request(
        self,
        registry_type: RegistryType,
        path: str,
        headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, Dict[str, str]]:
        """Build the upstream URL and request headers."""
        upstream_base = self.get_upstream(registry_type)
        if not upstream_base:
            return "", {}
        url = self._build_url(registry_type, upstream_base, path)
        request_headers = self._build_request_headers(headers)
        return url, request_headers

    @asynccontextmanager
    async def open_response(
        self,
        url: str,
        method: str,
        headers: Dict[str, str],
        body: Optional[bytes],
    ):
        """Open an upstream response as an async context manager."""
        if self._session is None:
            await self.start()
        assert self._session is not None
        async with self._session.request(
            method,
            url,
            headers=headers,
            data=body,
            allow_redirects=True,
        ) as response:
            yield response

    def cache_key(self, url: str, request_headers: Dict[str, str]) -> str:
        """Build a cache key that accounts for response variants."""
        lower = {k.lower(): v for k, v in request_headers.items()}
        accept = lower.get("accept", "")
        accept_encoding = lower.get("accept-encoding", "")
        return f"{url}\naccept={accept}\naccept-encoding={accept_encoding}"

    def is_cacheable_request(self, request_headers: Dict[str, str]) -> bool:
        """Determine if a request is safe to cache."""
        lower = {k.lower(): v for k, v in request_headers.items()}
        if "authorization" in lower:
            return False
        if "cookie" in lower:
            return False
        return True

    def is_cacheable_response(self, response_headers: Dict[str, Any]) -> bool:
        """Determine if a response is safe to cache."""
        lower = {k.lower(): str(v) for k, v in response_headers.items()}

        if "set-cookie" in lower:
            return False

        cache_control = lower.get("cache-control", "").lower()
        if any(token in cache_control for token in ("no-store", "no-cache", "private")):
            return False

        pragma = lower.get("pragma", "").lower()
        if "no-cache" in pragma:
            return False

        vary = lower.get("vary", "")
        if vary:
            vary_tokens = {token.strip().lower() for token in vary.split(",") if token.strip()}
            if "*" in vary_tokens:
                return False
            if not vary_tokens.issubset({"accept", "accept-encoding"}):
                return False

        return True

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

    def filter_response_headers(self, headers: Dict[str, Any]) -> Dict[str, str]:
        """Filter response headers to forward to client.

        Args:
            headers: Raw response headers.

        Returns:
            Filtered headers dict.
        """
        # Canonical header names to forward (lowercased for comparison)
        forward_headers = {
            "content-type": "Content-Type",
            "content-length": "Content-Length",
            "etag": "ETag",
            "last-modified": "Last-Modified",
            "cache-control": "Cache-Control",
            "content-encoding": "Content-Encoding",
        }

        filtered = {}
        for key, value in headers.items():
            canonical = forward_headers.get(key.lower())
            if canonical is not None:
                filtered[canonical] = str(value)

        return filtered

    async def __aenter__(self) -> "UpstreamClient":
        """Async context manager entry."""
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.stop()
