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


def _to_artifacts_list(obj):
    """Convert provider artifacts object to a list of dicts safely."""
    if isinstance(obj, list):
        return obj
    try:
        return list(obj)  # type: ignore[arg-type]
    except Exception:  # pylint: disable=broad-exception-caught
        return []


def _simplify_match_result(res):
    """Simplify match result artifact field to only include a 'name' key."""
    if not res or not isinstance(res, dict):
        return res
    artifact = res.get("artifact")
    if isinstance(artifact, dict):
        simplified = res.copy()
        simplified["artifact"] = {"name": res.get("tag_or_release", "")}
        return simplified
    return res


def _safe_get_releases(provider, owner: str, repo: str):
    """Fetch releases from provider, returning [] on errors."""
    try:
        rel = provider.get_releases(owner, repo)
        return rel or []
    except Exception:  # pylint: disable=broad-exception-caught
        return []


def _safe_get_tags(provider, owner: str, repo: str):
    """Fetch tags from provider if supported, returning [] when unavailable or on errors."""
    get_tags = getattr(provider, "get_tags", None)
    if not callable(get_tags):
        return []
    try:
        tags = get_tags(owner, repo)
        return tags or []
    except Exception:  # pylint: disable=broad-exception-caught
        return []


def _match_version(matcher, version: str, artifacts):
    """Run version matcher and normalize artifact shape."""
    try:
        res = matcher.find_match(version, artifacts)
    except Exception:  # pylint: disable=broad-exception-caught
        return None
    return _simplify_match_result(res)


def _choose_final_result(release_result, tag_result):
    """Prefer matched release, then any tag, then any release result."""
    if release_result and isinstance(release_result, dict) and release_result.get("matched", False):
        return release_result
    if tag_result:
        return tag_result
    return release_result
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
    ) -> bool:  # pylint: disable=too-many-locals,too-many-branches,too-many-statements,too-many-nested-blocks
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
        # If provider exposes a raw repo_info attribute and it is explicitly None,
        # honor it as "repo not found" for test doubles that signal absence this way.
        if hasattr(provider, "repo_info") and getattr(provider, "repo_info") is None:
            return False
        # Trust provider.get_repo_info as the source of truth; only treat explicit None as not found.
        if info is None:
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

        # Attempt version matching across releases, then optional fallback to tags
        m = matcher or VersionMatcher()
        empty_version = (version or "") == ""

        # Releases first
        rel_artifacts = _to_artifacts_list(_safe_get_releases(provider, ref.owner, ref.repo))
        release_result = _match_version(m, version, rel_artifacts) if rel_artifacts else None

        # Tags fallback only when version is not empty and releases didn't match
        tag_result = None
        if (
            not empty_version
            and not (
                release_result
                and isinstance(release_result, dict)
                and release_result.get('matched', False)
            )
        ):
            tag_artifacts = _to_artifacts_list(_safe_get_tags(provider, ref.owner, ref.repo))
            tag_result = _match_version(m, version, tag_artifacts) if tag_artifacts else None

        # Record match sources for downstream (non-breaking diagnostics)
        try:
            setattr(
                mp,
                "_version_match_release_matched",
                bool(
                    release_result
                    and isinstance(release_result, dict)
                    and release_result.get("matched", False)
                ),
            )
            setattr(
                mp,
                "_version_match_tag_matched",
                bool(
                    tag_result
                    and isinstance(tag_result, dict)
                    and tag_result.get("matched", False)
                ),
            )
            _src = (
                "release"
                if getattr(mp, "_version_match_release_matched", False)
                else ("tag" if getattr(mp, "_version_match_tag_matched", False) else None)
            )
            setattr(mp, "_repo_version_match_source", _src)
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        # Choose final result
        final_result = _choose_final_result(release_result, tag_result)
        if final_result is None:
            final_result = {
                'matched': False,
                'match_type': None,
                'artifact': None,
                'tag_or_release': None
            }
        mp.repo_version_match = final_result

        return True
