"""Shared validation service for repository provider enrichment.

Provides a unified interface for validating and populating MetaPackage
instances with repository data from any supported provider.
"""
from __future__ import annotations

import re
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


_BARE_VERSION_RE = re.compile(r'^v?\d+(?:\.\d+){1,3}(?:[-+][0-9A-Za-z.\-]+)?$')


def _is_monorepo_mismatch(pkg_name: str, release_result, tag_result) -> bool:
    """Detect when a repo's releases/tags are for different packages (monorepo).

    Returns True when the repo has artifacts but none appear to be versions
    for the given package — i.e., all tags/releases are scoped to other
    package names within the monorepo.

    A tag is considered "for this package" if it is either:
    - A bare version like ``v1.2.3`` (no package prefix), OR
    - Prefixed with the package name, e.g. ``@types/node@1.2.3``
    """
    # Collect artifact labels from both sources
    labels: list = []
    for result in (release_result, tag_result):
        if isinstance(result, dict):
            labels.extend(result.get('artifact_labels', []))

    if not labels:
        return False

    # Derive acceptable prefixes from the package name.
    # For "@types/node" we accept labels starting with "@types/node@" or "node@".
    # For "lodash" we accept labels starting with "lodash@".
    prefixes = []
    if pkg_name:
        prefixes.append(pkg_name + '@')
        # Unscoped suffix: @scope/name -> name
        if '/' in pkg_name:
            unscoped = pkg_name.rsplit('/', 1)[1]
            if unscoped:
                prefixes.append(unscoped + '@')

    for label in labels:
        # Bare version tags (no package prefix) are compatible with any package
        if _BARE_VERSION_RE.match(label):
            return False
        # Tag matches this package's name prefix
        for pfx in prefixes:
            if label.startswith(pfx):
                return False

    # All sampled tags are scoped to other packages — monorepo mismatch
    return True


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
        # Once we set repo_exists = True, we must ensure repo_version_match is always set
        # Wrap everything after setting repo_exists in try-except to guarantee this
        try:
            mp.repo_exists = True
            mp.repo_stars = info.get('stars')
            mp.repo_last_activity_at = info.get('last_activity_at')

            # Get contributor count if available
            try:
                contributors = provider.get_contributors_count(ref.owner, ref.repo)
                if contributors is not None:
                    mp.repo_contributors = contributors
            except Exception:  # pylint: disable=broad-exception-caught
                # Contributor count is optional, continue even if it fails
                pass

            # Attempt version matching across releases, then optional fallback to tags
            m = matcher or VersionMatcher()
            empty_version = (version or "") == ""

            # Releases first (use provider-optimized lookup when available)
            release_result = None
            find_release_match = getattr(provider, "find_release_match", None)
            if callable(find_release_match):
                optimized_release = find_release_match(ref.owner, ref.repo, version, m)
                if isinstance(optimized_release, dict) and "matched" in optimized_release:
                    release_result = optimized_release
                else:
                    rel_artifacts = _to_artifacts_list(_safe_get_releases(provider, ref.owner, ref.repo))
                    release_result = _match_version(m, version, rel_artifacts) if rel_artifacts else None
            else:
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
                find_tag_match = getattr(provider, "find_tag_match", None)
                if callable(find_tag_match):
                    optimized_tag = find_tag_match(ref.owner, ref.repo, version, m)
                    if isinstance(optimized_tag, dict) and "matched" in optimized_tag:
                        tag_result = optimized_tag
                    else:
                        tag_artifacts = _to_artifacts_list(_safe_get_tags(provider, ref.owner, ref.repo))
                        tag_result = _match_version(m, version, tag_artifacts) if tag_artifacts else None
                else:
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

            # When not matched, propagate whether the repo has any releases/tags at all.
            # This distinguishes "repo never uses tags" (not suspicious) from
            # "repo has tags for other versions but not this one" (suspicious).
            if not final_result.get('matched', False):
                has_releases = (
                    (isinstance(release_result, dict) and release_result.get('has_artifacts', False))
                    or bool(locals().get('rel_artifacts'))
                )
                has_tags = (
                    (isinstance(tag_result, dict) and tag_result.get('has_artifacts', False))
                    or bool(locals().get('tag_artifacts'))
                )
                has_any = has_releases or has_tags
                final_result['has_any_version_artifacts'] = has_any

                # Monorepo detection: if the repo has tags/releases but they
                # are all scoped to different package names, this is a monorepo
                # where the current package isn't individually tagged.
                # Treat like "never tags" (has_any_version_artifacts = False)
                # so the version match weight is redistributed.
                if has_any:
                    # Ensure artifact labels are available for monorepo detection.
                    # The optimized path populates artifact_labels in the result;
                    # for the non-optimized path, extract labels from local artifacts.
                    _max_sample = 20
                    for _src_result, _src_local in (
                        (release_result, 'rel_artifacts'),
                        (tag_result, 'tag_artifacts'),
                    ):
                        if (
                            isinstance(_src_result, dict)
                            and 'artifact_labels' not in _src_result
                        ):
                            _local_arts = locals().get(_src_local, []) or []
                            _labels = []
                            for _art in _local_arts[:_max_sample]:
                                _lbl = _art.get('tag_name') or _art.get('name') or ''
                                if _lbl:
                                    _labels.append(str(_lbl))
                            _src_result['artifact_labels'] = _labels

                    pkg_name = getattr(mp, 'pkg_name', '') or ''
                    if _is_monorepo_mismatch(pkg_name, release_result, tag_result):
                        final_result['has_any_version_artifacts'] = False

            mp.repo_version_match = final_result
        except Exception:  # pylint: disable=broad-exception-caught
            # If an exception occurs after setting repo_exists = True, we must ensure
            # repo_version_match is set to avoid None values in output
            # Only set it if repo_exists was successfully set (defensive check)
            if getattr(mp, "repo_exists", None) is True:
                mp.repo_version_match = {
                    'matched': False,
                    'match_type': None,
                    'artifact': None,
                    'tag_or_release': None
                }
            # If repo_exists wasn't set, we'll return False below, which is correct

        return True
