"""TTL cache for proxy decisions and responses."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, Generic, Optional, TypeVar

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """A single cache entry with TTL."""

    value: T
    expires_at: float
    created_at: float = field(default_factory=time.time)

    def is_expired(self) -> bool:
        """Check if this entry has expired."""
        return time.time() > self.expires_at


class DecisionCache:
    """TTL cache for policy decisions.

    Caches policy evaluation results to avoid repeated lookups
    for the same package/version combination.
    """

    def __init__(self, default_ttl: int = 3600):
        """Initialize the decision cache.

        Args:
            default_ttl: Default time-to-live in seconds.
        """
        self._default_ttl = default_ttl
        self._cache: Dict[str, CacheEntry[Dict[str, Any]]] = {}
        self._max_entries = 10000
        self._last_cleanup = time.time()
        self._cleanup_interval = 60  # Run cleanup every minute

    def _make_key(self, registry: str, package_name: str, version: Optional[str]) -> str:
        """Generate cache key."""
        version_part = version or "latest"
        return f"{registry}:{package_name}:{version_part}"

    def get(
        self, registry: str, package_name: str, version: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get a cached decision.

        Args:
            registry: Registry type (npm, pypi, etc).
            package_name: Package name.
            version: Optional version.

        Returns:
            Cached decision dict or None if not found/expired.
        """
        self._maybe_cleanup()

        key = self._make_key(registry, package_name, version)
        entry = self._cache.get(key)

        if entry is None:
            return None

        if entry.is_expired():
            del self._cache[key]
            return None

        return entry.value

    def set(
        self,
        registry: str,
        package_name: str,
        version: Optional[str],
        decision: Dict[str, Any],
        ttl: Optional[int] = None,
    ) -> None:
        """Cache a decision.

        Args:
            registry: Registry type.
            package_name: Package name.
            version: Optional version.
            decision: Decision dict to cache.
            ttl: Optional TTL override in seconds.
        """
        self._maybe_cleanup()

        key = self._make_key(registry, package_name, version)
        effective_ttl = ttl if ttl is not None else self._default_ttl
        expires_at = time.time() + effective_ttl

        self._cache[key] = CacheEntry(value=decision, expires_at=expires_at)

        # Evict oldest entries if over limit
        if len(self._cache) > self._max_entries:
            self._evict_oldest(self._max_entries // 10)

    def invalidate(
        self, registry: str, package_name: str, version: Optional[str] = None
    ) -> None:
        """Invalidate a cached entry.

        Args:
            registry: Registry type.
            package_name: Package name.
            version: Optional version. If None, invalidates all versions.
        """
        if version is not None:
            key = self._make_key(registry, package_name, version)
            self._cache.pop(key, None)
        else:
            # Invalidate all versions of this package
            prefix = f"{registry}:{package_name}:"
            keys_to_remove = [k for k in self._cache if k.startswith(prefix)]
            for key in keys_to_remove:
                del self._cache[key]

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        now = time.time()
        expired_count = sum(1 for e in self._cache.values() if e.is_expired())
        return {
            "total_entries": len(self._cache),
            "expired_entries": expired_count,
            "active_entries": len(self._cache) - expired_count,
            "max_entries": self._max_entries,
            "default_ttl": self._default_ttl,
        }

    def _maybe_cleanup(self) -> None:
        """Run cleanup if enough time has passed."""
        now = time.time()
        if now - self._last_cleanup > self._cleanup_interval:
            self._cleanup()
            self._last_cleanup = now

    def _cleanup(self) -> None:
        """Remove expired entries."""
        keys_to_remove = [k for k, v in self._cache.items() if v.is_expired()]
        for key in keys_to_remove:
            del self._cache[key]

    def _evict_oldest(self, count: int) -> None:
        """Evict the oldest entries."""
        # Sort by creation time
        sorted_keys = sorted(
            self._cache.keys(), key=lambda k: self._cache[k].created_at
        )
        for key in sorted_keys[:count]:
            del self._cache[key]


class ResponseCache:
    """TTL cache for upstream responses.

    Caches raw responses from upstream registries to reduce
    latency and load on upstream servers.
    """

    def __init__(self, default_ttl: int = 300):
        """Initialize the response cache.

        Args:
            default_ttl: Default time-to-live in seconds.
        """
        self._default_ttl = default_ttl
        self._cache: Dict[str, CacheEntry[bytes]] = {}
        self._headers_cache: Dict[str, Dict[str, str]] = {}
        self._max_entries = 1000
        self._max_bytes = 100 * 1024 * 1024  # 100MB
        self._current_bytes = 0
        self._last_cleanup = time.time()
        self._cleanup_interval = 30

    def get(self, url: str) -> Optional[tuple[bytes, Dict[str, str]]]:
        """Get a cached response.

        Args:
            url: Request URL.

        Returns:
            Tuple of (body bytes, headers dict) or None if not found/expired.
        """
        self._maybe_cleanup()

        entry = self._cache.get(url)
        if entry is None:
            return None

        if entry.is_expired():
            self._remove_entry(url)
            return None

        headers = self._headers_cache.get(url, {})
        return entry.value, headers

    def set(
        self,
        url: str,
        body: bytes,
        headers: Dict[str, str],
        ttl: Optional[int] = None,
    ) -> None:
        """Cache a response.

        Args:
            url: Request URL.
            body: Response body bytes.
            headers: Response headers.
            ttl: Optional TTL override in seconds.
        """
        self._maybe_cleanup()

        # Check if response is too large
        body_size = len(body)
        if body_size > self._max_bytes // 10:
            # Don't cache responses larger than 10% of max cache size
            return

        # Evict if needed to make room
        while self._current_bytes + body_size > self._max_bytes and self._cache:
            self._evict_oldest(1)

        # Remove existing entry if present
        if url in self._cache:
            self._remove_entry(url)

        effective_ttl = ttl if ttl is not None else self._default_ttl
        expires_at = time.time() + effective_ttl

        self._cache[url] = CacheEntry(value=body, expires_at=expires_at)
        self._headers_cache[url] = headers
        self._current_bytes += body_size

        # Evict if over entry limit
        if len(self._cache) > self._max_entries:
            self._evict_oldest(self._max_entries // 10)

    def invalidate(self, url: str) -> None:
        """Invalidate a cached response."""
        self._remove_entry(url)

    def clear(self) -> None:
        """Clear all cached responses."""
        self._cache.clear()
        self._headers_cache.clear()
        self._current_bytes = 0

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        expired_count = sum(1 for e in self._cache.values() if e.is_expired())
        return {
            "total_entries": len(self._cache),
            "expired_entries": expired_count,
            "active_entries": len(self._cache) - expired_count,
            "current_bytes": self._current_bytes,
            "max_bytes": self._max_bytes,
            "max_entries": self._max_entries,
            "default_ttl": self._default_ttl,
        }

    def _remove_entry(self, url: str) -> None:
        """Remove an entry and update byte count."""
        entry = self._cache.pop(url, None)
        self._headers_cache.pop(url, None)
        if entry:
            self._current_bytes -= len(entry.value)

    def _maybe_cleanup(self) -> None:
        """Run cleanup if enough time has passed."""
        now = time.time()
        if now - self._last_cleanup > self._cleanup_interval:
            self._cleanup()
            self._last_cleanup = now

    def _cleanup(self) -> None:
        """Remove expired entries."""
        urls_to_remove = [url for url, entry in self._cache.items() if entry.is_expired()]
        for url in urls_to_remove:
            self._remove_entry(url)

    def _evict_oldest(self, count: int) -> None:
        """Evict the oldest entries."""
        sorted_urls = sorted(
            self._cache.keys(), key=lambda u: self._cache[u].created_at
        )
        for url in sorted_urls[:count]:
            self._remove_entry(url)
