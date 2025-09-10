"""Shared validation service for repository provider enrichment.

Provides a unified interface for validating and populating MetaPackage
instances with repository data from any supported provider.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List
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

        # Attempt version matching across releases, then fall back to tags if no match
        m = matcher or VersionMatcher()

        release_result = None
        try:
            releases = provider.get_releases(ref.owner, ref.repo)
        except Exception:
            releases = None

        if releases:
            artifacts_list: List[Dict[str, Any]] = releases if isinstance(releases, list) else []
            if not artifacts_list:
                try:
                    artifacts_list = list(releases)  # type: ignore[arg-type]
                except Exception:
                    artifacts_list = []
            release_result = m.find_match(version, artifacts_list)
            # Maintain backward compatibility: artifact should only contain name field
            if (
                release_result
                and isinstance(release_result, dict)
                and release_result.get('artifact')
                and isinstance(release_result['artifact'], dict)
            ):
                simplified_artifact = {'name': release_result.get('tag_or_release', '')}
                release_result = release_result.copy()
                release_result['artifact'] = simplified_artifact

        # If no match from releases (or none available), try tags even when releases exist
        tag_result = None
        get_tags = getattr(provider, "get_tags", None)
        if (not release_result) or (not release_result.get('matched', False)):
            if callable(get_tags):
                try:
                    tags = get_tags(ref.owner, ref.repo)
                    if tags:
                        artifacts_list: List[Dict[str, Any]] = tags if isinstance(tags, list) else []
                        if not artifacts_list:
                            try:
                                artifacts_list = list(tags)  # type: ignore[arg-type]
                            except Exception:
                                artifacts_list = []
                        tag_result = m.find_match(version, artifacts_list)
                        # Maintain backward compatibility: artifact should only contain name field
                        if (
                            tag_result
                            and isinstance(tag_result, dict)
                            and tag_result.get('artifact')
                            and isinstance(tag_result['artifact'], dict)
                        ):
                            simplified_artifact = {'name': tag_result.get('tag_or_release', '')}
                            tag_result = tag_result.copy()
                            tag_result['artifact'] = simplified_artifact
                except Exception:
                    pass

        # Choose final result: prefer a matched release, else matched tag, else last attempted result
        final_result = None
        if release_result and release_result.get('matched', False):
            final_result = release_result
        elif tag_result:
            final_result = tag_result
        elif release_result:
            final_result = release_result

        if final_result is not None:
            mp.repo_version_match = final_result

        return True
