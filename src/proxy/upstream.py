"""Upstream client for forwarding requests to real registries."""

from __future__ import annotations

import logging
import urllib.parse
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
    DEFAULT_REDIRECT_ALLOWLIST = {
        RegistryType.NPM: set(),
        RegistryType.PYPI: {"files.pythonhosted.org"},
        RegistryType.MAVEN: {"repo.maven.apache.org"},
        RegistryType.NUGET: {"globalcdn.nuget.org"},
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
        self._redirect_allowlist = {
            registry: set(hosts) for registry, hosts in self.DEFAULT_REDIRECT_ALLOWLIST.items()
        }

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
        response = await self._request_with_redirects(
            url,
            method,
            headers,
            body,
        )
        try:
            yield response
        finally:
            response.release()

    def cache_key(self, url: str, request_headers: Dict[str, str]) -> str:
        """Build a cache key that accounts for response variants."""
        lower = {k.lower(): v for k, v in request_headers.items()}
        accept = lower.get("accept", "")
        accept_encoding = lower.get("accept-encoding", "")
        return f"{url}\naccept={accept}\naccept-encoding={accept_encoding}"

    def _registry_type_for_url(self, url: str) -> Optional[RegistryType]:
        """Infer registry type based on the upstream base URL."""
        matches = []
        for registry_type, upstream in self._upstreams.items():
            if not upstream:
                continue
            base = upstream.rstrip("/")
            if url.startswith(base):
                matches.append((len(base), registry_type))
        if not matches:
            return None
        matches.sort(key=lambda item: item[0], reverse=True)
        return matches[0][1]

    def _is_allowed_redirect(self, source_url: str, target_url: str) -> bool:
        """Validate redirect targets to prevent SSRF."""
        target = urllib.parse.urlparse(target_url)
        if target.scheme not in ("http", "https"):
            return False
        if not target.hostname:
            return False

        registry_type = self._registry_type_for_url(source_url)
        allowed_hosts = set()

        if registry_type is not None:
            upstream_host = urllib.parse.urlparse(
                self.get_upstream(registry_type)
            ).hostname
            if upstream_host:
                allowed_hosts.add(upstream_host.lower())
            allowed_hosts.update(
                host.lower() for host in self._redirect_allowlist.get(registry_type, set())
            )
        else:
            source_host = urllib.parse.urlparse(source_url).hostname
            if source_host:
                allowed_hosts.add(source_host.lower())

        target_host = target.hostname.lower()
        for host in allowed_hosts:
            if target_host == host or target_host.endswith(f".{host}"):
                return True
        return False

    async def _request_with_redirects(
        self,
        url: str,
        method: str,
        headers: Dict[str, str],
        body: Optional[bytes],
        max_redirects: int = 5,
    ) -> aiohttp.ClientResponse:
        """Request URL while enforcing a redirect allowlist."""
        assert self._session is not None
        current_url = url
        current_method = method
        current_body = body

        for _ in range(max_redirects + 1):
            response = await self._session.request(
                current_method,
                current_url,
                headers=headers,
                data=current_body,
                allow_redirects=False,
            )

            if response.status not in (301, 302, 303, 307, 308):
                return response

            location = response.headers.get("Location")
            if not location:
                return response

            next_url = urllib.parse.urljoin(current_url, location)
            if not self._is_allowed_redirect(current_url, next_url):
                response.release()
                raise aiohttp.ClientError("Redirect blocked by allowlist")

            # Only follow redirects that preserve method for non-GET/HEAD.
            if current_method not in ("GET", "HEAD") and response.status in (301, 302, 303):
                response.release()
                raise aiohttp.ClientError("Redirect not allowed for non-GET/HEAD request")

            # 303 forces GET per RFC; drop body.
            if response.status == 303:
                current_method = "GET"
                current_body = None

            response.release()
            current_url = next_url

        raise aiohttp.ClientError("Too many redirects")

    def is_cacheable_request(self, request_headers: Dict[str, str]) -> bool:
        """Determine if a request is safe to cache."""
        lower = {k.lower(): v for k, v in request_headers.items()}
        if "authorization" in lower:
            return False
        if "cookie" in lower:
            return False
        if "range" in lower:
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
            "proxy-connection",
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
            "accept-ranges": "Accept-Ranges",
            "cache-control": "Cache-Control",
            "content-disposition": "Content-Disposition",
            "content-encoding": "Content-Encoding",
            "content-length": "Content-Length",
            "content-range": "Content-Range",
            "content-type": "Content-Type",
            "etag": "ETag",
            "last-modified": "Last-Modified",
            "location": "Location",
            "retry-after": "Retry-After",
            "vary": "Vary",
            "www-authenticate": "WWW-Authenticate",
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
