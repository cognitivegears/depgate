"""Base class for version resolvers."""

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from ..cache import TTLCache
from ..models import Ecosystem, PackageRequest


class VersionResolver(ABC):
    """Abstract base class for ecosystem-specific version resolvers."""

    def __init__(self, cache: Optional["TTLCache"] = None) -> None:
        """Initialize resolver with optional cache.

        Args:
            cache: Optional TTL cache for metadata
        """
        self.cache = cache

    @property
    @abstractmethod
    def ecosystem(self) -> Ecosystem:
        """Return the ecosystem this resolver handles."""
        pass

    @abstractmethod
    def fetch_candidates(self, req: PackageRequest) -> List[str]:
        """Fetch list of available version strings for the package.

        Args:
            req: Package resolution request

        Returns:
            List of version strings (may be unsorted)
        """
        pass

    @abstractmethod
    def pick(
        self, req: PackageRequest, candidates: List[str]
    ) -> Tuple[Optional[str], int, Optional[str]]:
        """Apply version spec semantics to select best matching version.

        Args:
            req: Package resolution request
            candidates: List of available version strings

        Returns:
            Tuple of (resolved_version, candidate_count_considered, error_message)
            - resolved_version: Selected version string or None if no match
            - candidate_count_considered: Number of candidates evaluated
            - error_message: Error description if resolution failed, None otherwise
        """
        pass
