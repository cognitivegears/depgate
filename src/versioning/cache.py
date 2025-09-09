"""Simple in-memory TTL cache for version resolution metadata."""

import time
from typing import Any, Dict, Optional, Tuple


class TTLCache:
    """Simple in-memory TTL cache with thread-unsafe implementation for CLI usage."""

    def __init__(self) -> None:
        """Initialize empty cache."""
        self._cache: Dict[str, Tuple[Any, float]] = {}

    def get(self, key: str) -> Optional[Any]:
        """Retrieve value from cache if not expired.

        Args:
            key: Cache key to look up

        Returns:
            Cached value if present and not expired, None otherwise
        """
        if key not in self._cache:
            return None

        value, expires_at = self._cache[key]
        if time.time() > expires_at:
            # Entry expired, remove it
            del self._cache[key]
            return None

        return value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """Store value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time to live in seconds
        """
        expires_at = time.time() + ttl_seconds
        self._cache[key] = (value, expires_at)
