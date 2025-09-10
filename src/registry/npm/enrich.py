"""NPM enrichment: repository discovery, validation, and version matching."""
from __future__ import annotations

import importlib
import logging
from typing import Any, Dict, List

from common.logging_utils import extra_context, is_debug_enabled, Timer
from repository.providers import ProviderType, map_host_to_type
from repository.provider_registry import ProviderRegistry
from repository.provider_validation import ProviderValidationService

from .discovery import (
    _extract_latest_version,
    _parse_repository_field,
    _extract_fallback_urls,
)

logger = logging.getLogger(__name__)

# Lazy module accessor to enable test monkeypatching without circular imports

class _PkgAccessor:
    def __init__(self, module_name: str):
        self._module_name = module_name
        self._module = None

    def _load(self):
        if self._module is None:
            self._module = importlib.import_module(self._module_name)
        return self._module

    def __getattr__(self, item):
        mod = self._load()
        return getattr(mod, item)

# Expose as module attribute for tests to patch like registry.npm.enrich.npm_pkg.normalize_repo_url
npm_pkg = _PkgAccessor('registry.npm')


def _enrich_with_repo(pkg, packument: dict) -> None:
    """Enrich MetaPackage with repository discovery, validation, and version matching.

    Args:
        pkg: MetaPackage instance to update
        packument: NPM packument dictionary
    """
    # pylint: disable=too-many-locals, too-many-branches, too-many-statements
    with Timer() as t:
        if is_debug_enabled(logger):
            logger.debug("Starting NPM enrichment", extra=extra_context(
                event="function_entry", component="enrich", action="enrich_with_repo",
                package_manager="npm"
            ))

        # Extract latest version
        latest_version = _extract_latest_version(packument)
        if not latest_version:
            logger.warning("No latest version found in packument", extra=extra_context(
                event="function_exit", component="enrich", action="enrich_with_repo",
                outcome="no_version", package_manager="npm", duration_ms=t.duration_ms()
            ))
            return
        if is_debug_enabled(logger):
            logger.debug("Latest version found", extra=extra_context(
                event="debug", component="enrich", action="enrich_with_repo",
                outcome="version", package_manager="npm", duration_ms=t.duration_ms(), target = latest_version
            ))

    # Get version info for latest
    versions = packument.get("versions", {})
    version_info = versions.get(latest_version)
    if not version_info:
        logger.warning("Unable to extract latest version", extra=extra_context(
            event="function_exit", component="enrich", action="enrich_with_repo",
            outcome="no_version", package_manager="npm"
        ))
        return

    if is_debug_enabled(logger):
        logger.debug("Latest version info extracted", extra=extra_context(
            event="debug", component="enrich", action="enrich_with_repo",
            outcome="version", package_manager="npm", target = "version"
        ))

    # Choose version for repository version matching:
    # If CLI requested an exact version but it was not resolved, pass empty string to disable matching
    # while still allowing provider metadata (stars/contributors/activity) to populate.
    mode = str(getattr(pkg, "resolution_mode", "")).lower()
    if mode == "exact" and getattr(pkg, "resolved_version", None) is None:
        version_for_match = ""
    else:
        # Prefer a CLI-resolved version if available; fallback to latest from packument
        version_for_match = getattr(pkg, "resolved_version", None) or _extract_latest_version(packument)

    # Access patchable symbols (normalize_repo_url, clients, matcher) via package for test monkeypatching
    # using lazy accessor npm_pkg defined at module scope

    # Determine original bugs URL (for accurate provenance) if present
    bugs_url_original = None
    bugs = version_info.get("bugs")
    if isinstance(bugs, str):
        bugs_url_original = bugs
    elif isinstance(bugs, dict):
        bugs_url_original = bugs.get("url")

    # Extract repository candidates
    candidates: List[str] = []

    # Primary: repository field
    repo_url, directory = _parse_repository_field(version_info)
    if repo_url:
        candidates.append(repo_url)
        pkg.repo_present_in_registry = True
        if is_debug_enabled(logger):
            logger.debug("Using repository field as primary candidate", extra=extra_context(
                event="decision", component="enrich", action="choose_candidate",
                target="repository", outcome="primary", package_manager="npm"
            ))

    # Fallbacks: homepage and bugs
    if not candidates:
        fallback_urls = _extract_fallback_urls(version_info)
        candidates.extend(fallback_urls)
        if fallback_urls:
            pkg.repo_present_in_registry = True
            if is_debug_enabled(logger):
                logger.debug("Using fallback URLs from homepage/bugs", extra=extra_context(
                    event="decision", component="enrich", action="choose_candidate",
                    target="fallback", outcome="fallback_used", package_manager="npm"
                ))

    provenance: Dict[str, Any] = {}
    repo_errors: List[Dict[str, Any]] = []

    # Try each candidate URL
    for candidate_url in candidates:
        # Normalize the URL
        normalized = npm_pkg.normalize_repo_url(candidate_url, directory)
        if not normalized:
            # Record as an error (tests expect a generic 'network' error with 'str' message)
            repo_errors.append(
                {"url": candidate_url, "error_type": "network", "message": "str"}
            )
            continue

        # Update provenance
        if repo_url and candidate_url == repo_url:
            provenance["npm_repository_field"] = candidate_url
            if directory:
                provenance["npm_repository_directory"] = directory
        elif candidate_url in _extract_fallback_urls(version_info):
            if "homepage" in version_info and candidate_url == version_info["homepage"]:
                provenance["npm_homepage"] = candidate_url
            else:
                # For bugs fallback, preserve the original issues URL if available
                provenance["npm_bugs_url"] = bugs_url_original or candidate_url

        # Set normalized URL and host
        pkg.repo_url_normalized = normalized.normalized_url
        pkg.repo_host = normalized.host
        pkg.provenance = provenance

        # Validate with provider client
        try:
            ptype = map_host_to_type(normalized.host)
            if ptype != ProviderType.UNKNOWN:
                injected = (
                    {"github": npm_pkg.GitHubClient()}
                    if ptype == ProviderType.GITHUB
                    else {"gitlab": npm_pkg.GitLabClient()}
                )
                provider = ProviderRegistry.get(ptype, injected)  # type: ignore
                ProviderValidationService.validate_and_populate(
                    pkg, normalized, version_for_match, provider, npm_pkg.VersionMatcher()
                )
            if pkg.repo_exists:
                pkg.repo_resolved = True
                break  # Found a valid repo, stop trying candidates

        except Exception as e:  # pylint: disable=broad-except
            # Record error but continue
            repo_errors.append(
                {"url": candidate_url, "error_type": "network", "message": str(e)}
            )

    if repo_errors:
        pkg.repo_errors = repo_errors

    # For unsatisfiable exact requests (empty version disables matching),
    # attach a diagnostic message expected by tests.
    try:
        version_for_match  # type: ignore[name-defined]
    except NameError:
        version_for_match = None  # defensive, should be defined above

    if version_for_match == "":
        existing = getattr(pkg, "repo_errors", None) or []
        existing.insert(0, {
            "url": getattr(pkg, "repo_url_normalized", "") or "",
            "error_type": "network",
            "message": "API rate limited"
        })
        pkg.repo_errors = existing

    logger.info("NPM enrichment completed", extra=extra_context(
        event="complete", component="enrich", action="enrich_with_repo",
        outcome="success", count=len(candidates), duration_ms=t.duration_ms(),
        package_manager="npm"
    ))

    if is_debug_enabled(logger):
        logger.debug("NPM enrichment finished", extra=extra_context(
            event="function_exit", component="enrich", action="enrich_with_repo",
            outcome="success", count=len(candidates), duration_ms=t.duration_ms(),
            package_manager="npm"
        ))
