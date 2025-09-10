"""Provider type definitions and abstract client interface.

Provides type-safe provider selection and a common interface for repository
clients to enable provider-agnostic validation and enrichment.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Dict, List


class ProviderType(Enum):
    """Enumeration of supported repository providers."""
    GITHUB = 'github'
    GITLAB = 'gitlab'
    UNKNOWN = 'unknown'


def map_host_to_type(host: Optional[str]) -> ProviderType:
    """Map a host string to a ProviderType.

    Args:
        host: Host string (e.g., 'github', 'github.com', 'gitlab.com')

    Returns:
        ProviderType: Corresponding provider type
    """
    if not host:
        return ProviderType.UNKNOWN

    host_lower = host.lower()
    if 'github' in host_lower:
        return ProviderType.GITHUB
    if 'gitlab' in host_lower:
        return ProviderType.GITLAB
    return ProviderType.UNKNOWN


class ProviderClient(ABC):
    """Abstract base class for repository provider clients.

    Defines the common interface that all provider clients must implement
    to enable provider-agnostic repository validation and enrichment.
    """

    @abstractmethod
    def provider_name(self) -> str:
        """Return the name of the provider (e.g., 'github', 'gitlab').

        Returns:
            str: Provider name
        """
        raise NotImplementedError

    @abstractmethod
    def get_repo_info(self, owner: str, repo: str) -> Optional[Dict[str, Optional[str]]]:
        """Fetch repository metadata.

        Args:
            owner: Repository owner/organization name
            repo: Repository name

        Returns:
            Dict with normalized keys {'stars': int|None, 'last_activity_at': str|None}
            or None if repository doesn't exist or fetch failed
        """
        raise NotImplementedError

    @abstractmethod
    def get_contributors_count(self, owner: str, repo: str) -> Optional[int]:
        """Get contributor count for the repository.

        Args:
            owner: Repository owner/organization name
            repo: Repository name

        Returns:
            Contributor count or None if unavailable
        """
        raise NotImplementedError

    @abstractmethod
    def get_releases(self, owner: str, repo: str) -> List[Dict[str, str]]:
        """Fetch repository releases/tags for version matching.

        Args:
            owner: Repository owner/organization name
            repo: Repository name

        Returns:
            List of release/tag dictionaries for version matching
        """
        raise NotImplementedError

    @abstractmethod
    def get_tags(self, owner: str, repo: str) -> List[Dict[str, str]]:
        """Fetch repository tags for version matching.

        Args:
            owner: Repository owner/organization name
            repo: Repository name

        Returns:
            List of tag dictionaries for version matching
        """
        raise NotImplementedError
