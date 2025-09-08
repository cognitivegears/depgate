"""Shared validation service for repository provider enrichment.

Provides a unified interface for validating and populating MetaPackage
instances with repository data from any supported provider.
"""
from __future__ import annotations

from typing import TYPE_CHECKING
from .version_match import VersionMatcher

if TYPE_CHECKING:
    from .url_normalize import RepoRef
    from .providers import ProviderClient


class ProviderValidationService:  # pylint: disable=too-few-public-methods
    """Service for validating repositories and populating MetaPackage data.

    Mirrors the validation logic from existing registry implementations
    to ensure consistent behavior across all providers.
    """

    @staticmethod
    def validate_and_populate(
        mp,
        ref: 'RepoRef',
        version: str,
        provider: 'ProviderClient',
        matcher=None,
    ) -> bool:
        """Validate repository and populate MetaPackage with provider data.

        Args:
            mp: MetaPackage instance to update
            ref: RepoRef from url_normalize with owner/repo info
            version: Package version string for matching
            provider: ProviderClient instance to use for API calls

        Returns:
            True if repository exists and was successfully validated,
            False if repository doesn't exist or validation failed

        Note:
            This method mirrors the existing validation semantics from
            npm/pypi/maven registry implementations for backward compatibility.
        """
        # Get repository info
        info = provider.get_repo_info(ref.owner, ref.repo)
        if not info:
            # Repository doesn't exist or fetch failed
            return False

        # Populate repository existence and metadata
        mp.repo_exists = True
        mp.repo_stars = info.get('stars')
        mp.repo_last_activity_at = info.get('last_activity_at')

        # Get contributor count if available
        contributors = provider.get_contributors_count(ref.owner, ref.repo)
        if contributors is not None:
            mp.repo_contributors = contributors

        # Get releases and attempt version matching
        releases = provider.get_releases(ref.owner, ref.repo)
        if releases:
            m = matcher or VersionMatcher()
            match_result = m.find_match(version, releases)
            # Maintain backward compatibility: artifact should only contain name field
            if (
                match_result
                and isinstance(match_result, dict)
                and match_result.get('artifact')
                and isinstance(match_result['artifact'], dict)
            ):
                # Create simplified artifact with just the name for backward compatibility
                simplified_artifact = {
                    'name': match_result.get('tag_or_release', '')
                }
                match_result = match_result.copy()
                match_result['artifact'] = simplified_artifact
            mp.repo_version_match = match_result

        return True
