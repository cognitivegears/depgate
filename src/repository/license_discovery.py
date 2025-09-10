"""License discovery utility for fetching license information from repositories."""

import functools
import logging
from typing import Dict, Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class LicenseDiscovery:
    """Utility for discovering license information from repositories."""

    def __init__(self, cache_maxsize: int = 256):
        """Initialize LicenseDiscovery.

        Args:
            cache_maxsize: Maximum size of the LRU cache.
        """
        self.cache_maxsize = cache_maxsize
        # Use name-mangled private attributes to align with tests that patch them
        self.__discover_license = self._create_cached_discover_license()

    def _create_cached_discover_license(self):
        """Create a cached version of the license discovery function."""

        @functools.lru_cache(maxsize=self.cache_maxsize)
        def discover_license_cached(repo_url: str, ref: str = "default") -> Dict[str, Any]:
            """Cached license discovery function.

            Args:
                repo_url: Repository URL.
                ref: Reference (branch/tag), defaults to "default".

            Returns:
                Dict with license information.
            """
            return self.__discover_license_impl(repo_url, ref)

        return discover_license_cached

    def discover_license(self, repo_url: str, ref: str = "default") -> Dict[str, Any]:
        """Discover license information for a repository.

        Args:
            repo_url: Repository URL.
            ref: Reference (branch/tag), defaults to "default".

        Returns:
            Dict with license fields: id, available, source.
        """
        try:
            return self.__discover_license(repo_url, ref)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.warning("License discovery failed for %s: %s", repo_url, str(e))
            return {
                "id": None,
                "available": False,
                "source": None,
            }

    def __discover_license_impl(self, repo_url: str, ref: str) -> Dict[str, Any]:
        """Implementation of license discovery.

        Args:
            repo_url: Repository URL.
            ref: Reference (branch/tag).

        Returns:
            Dict with license information.
        """
        # Parse repository URL to determine provider
        parsed = urlparse(repo_url)
        provider = self._identify_provider(parsed)

        if provider == "github":
            return self._discover_github_license(repo_url, ref)
        if provider == "gitlab":
            return self._discover_gitlab_license(repo_url, ref)
        # Fallback: try generic license file discovery
        return self._discover_generic_license(repo_url, ref)

    def _identify_provider(self, parsed_url) -> str:
        """Identify the repository provider from URL.

        Args:
            parsed_url: Parsed URL object.

        Returns:
            Provider name: "github", "gitlab", or "other".
        """
        hostname = parsed_url.hostname
        if hostname in ("github.com", "www.github.com"):
            return "github"
        if hostname in ("gitlab.com", "www.gitlab.com"):
            return "gitlab"
        return "other"

    def _discover_github_license(self, repo_url: str, ref: str) -> Dict[str, Any]:  # noqa: ARG002
        """Discover license from GitHub repository.

        Args:
            repo_url: GitHub repository URL.
            ref: Reference (branch/tag).

        Returns:
            Dict with license information.
        """
        # Placeholder implementation - would integrate with GitHub API
        # For now, return unknown
        return {
            "id": None,
            "available": False,
            "source": "github_api",
        }

    def _discover_gitlab_license(self, repo_url: str, ref: str) -> Dict[str, Any]:  # noqa: ARG002
        """Discover license from GitLab repository.

        Args:
            repo_url: GitLab repository URL.
            ref: Reference (branch/tag).

        Returns:
            Dict with license information.
        """
        # Placeholder implementation - would integrate with GitLab API
        # For now, return unknown
        return {
            "id": None,
            "available": False,
            "source": "gitlab_api",
        }

    def _discover_generic_license(self, repo_url: str, ref: str) -> Dict[str, Any]:  # noqa: ARG002
        """Generic license discovery fallback.

        Args:
            repo_url: Repository URL.
            ref: Reference (branch/tag).

        Returns:
            Dict with license information.
        """
        # Placeholder implementation - would try to fetch common license files
        # For now, return unknown
        return {
            "id": None,
            "available": False,
            "source": "generic_fallback",
        }


# Global instance
license_discovery = LicenseDiscovery()
