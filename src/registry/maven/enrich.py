"""Maven enrichment: repository discovery, validation, and version matching."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from common.logging_utils import extra_context, is_debug_enabled, Timer
from repository.providers import ProviderType, map_host_to_type
from repository.provider_registry import ProviderRegistry
from repository.provider_validation import ProviderValidationService

from .discovery import (
    _resolve_latest_version,
    _traverse_for_scm,
    _normalize_scm_to_repo_url,
    _fetch_pom,
    _artifact_pom_url,
    _url_fallback_from_pom,
)

logger = logging.getLogger(__name__)

# Lazy module accessor to enable test monkeypatching without circular imports
import importlib

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

# Expose as module attribute for tests to patch like registry.maven.enrich.maven_pkg.normalize_repo_url
maven_pkg = _PkgAccessor('registry.maven')


def _enrich_with_repo(mp, group: str, artifact: str, version: Optional[str]) -> None:
    """Enrich MetaPackage with repository discovery, validation, and version matching.

    Args:
        mp: MetaPackage instance to update
        group: Maven group ID
        artifact: Maven artifact ID
        version: Version string (may be None)
    """
    with Timer() as t:
        if is_debug_enabled(logger):
            logger.debug("Starting Maven enrichment", extra=extra_context(
                event="function_entry", component="enrich", action="enrich_with_repo",
                package_manager="maven"
            ))
        # Milestone start
        logger.info("Maven enrichment started", extra=extra_context(
            event="start", component="enrich", action="enrich_with_repo",
            package_manager="maven"
        ))

        # Access patchable symbols via package for test monkeypatching (lazy accessor maven_pkg)

        # Resolve version if not provided
        if not version:
            version = maven_pkg._resolve_latest_version(group, artifact)
            if version:
                provenance = mp.provenance or {}
                provenance["maven_metadata.release"] = version
                mp.provenance = provenance
                if is_debug_enabled(logger):
                    logger.debug("Resolved latest version from Maven metadata", extra=extra_context(
                        event="decision", component="enrich", action="resolve_version",
                        target="maven-metadata.xml", outcome="resolved", package_manager="maven"
                    ))

        if not version:
            if is_debug_enabled(logger):
                logger.debug("No version available for Maven enrichment", extra=extra_context(
                    event="function_exit", component="enrich", action="enrich_with_repo",
                    outcome="no_version", package_manager="maven", duration_ms=t.duration_ms()
                ))
            return

    provenance: Dict[str, Any] = mp.provenance or {}
    repo_errors: List[Dict[str, Any]] = []

    # Try to get SCM from POM traversal
    if is_debug_enabled(logger):
        logger.debug("Starting SCM traversal for Maven POM", extra=extra_context(
            event="function_entry", component="enrich", action="traverse_for_scm",
            package_manager="maven"
        ))
    scm_info = maven_pkg._traverse_for_scm(group, artifact, version, provenance)
    # Allow _traverse_for_scm to return either a plain SCM dict or a wrapper with keys
    # 'scm' (dict) and optional 'provenance' (dict) for additional context.
    if isinstance(scm_info, dict) and "provenance" in scm_info and isinstance(scm_info["provenance"], dict):
        # Merge any provenance supplied by traversal
        provenance.update(scm_info["provenance"])
        mp.provenance = provenance
    if isinstance(scm_info, dict) and "scm" in scm_info and isinstance(scm_info["scm"], dict):
        scm_info = scm_info["scm"]

    candidates: List[str] = []

    # Primary: SCM from POM
    if scm_info:
        repo_url = _normalize_scm_to_repo_url(scm_info)
        if repo_url:
            candidates.append(repo_url)
            mp.repo_present_in_registry = True
            if is_debug_enabled(logger):
                logger.debug("Using SCM URL from POM traversal", extra=extra_context(
                    event="decision", component="enrich", action="choose_candidate",
                    target="scm", outcome="primary", package_manager="maven"
                ))

    # Fallback: <url> field from POM
    if not candidates:
        if is_debug_enabled(logger):
            logger.debug("No SCM found, trying URL fallback from POM", extra=extra_context(
                event="decision", component="enrich", action="choose_candidate",
                target="url_fallback", outcome="attempting", package_manager="maven"
            ))
        pom_xml = _fetch_pom(group, artifact, version)
        if pom_xml:
            fallback_url = _url_fallback_from_pom(pom_xml)
            if fallback_url:
                candidates.append(fallback_url)
                mp.repo_present_in_registry = True
                provenance["maven_pom.url_fallback"] = fallback_url
                if is_debug_enabled(logger):
                    logger.debug("Using URL fallback from POM", extra=extra_context(
                        event="decision", component="enrich", action="choose_candidate",
                        target="url_fallback", outcome="fallback_used", package_manager="maven"
                    ))

    # Try each candidate URL
    for candidate_url in candidates:
        # Normalize the URL (use package-level for test monkeypatching)
        normalized = maven_pkg.normalize_repo_url(candidate_url)
        if not normalized:
            continue

        # Set normalized URL and host
        mp.repo_url_normalized = normalized.normalized_url
        mp.repo_host = normalized.host
        mp.provenance = provenance

        # Validate with provider client
        try:
            ptype = map_host_to_type(normalized.host)
            if ptype != ProviderType.UNKNOWN:
                injected = (
                    {"github": maven_pkg.GitHubClient()}
                    if ptype == ProviderType.GITHUB
                    else {"gitlab": maven_pkg.GitLabClient()}
                )
                provider = ProviderRegistry.get(ptype, injected)  # type: ignore
                ProviderValidationService.validate_and_populate(
                    mp, normalized, version, provider, maven_pkg.VersionMatcher()
                )
            if mp.repo_exists:
                mp.repo_resolved = True
                break  # Found a valid repo, stop trying candidates

        except Exception as e:  # pylint: disable=broad-except
            # Record error but continue
            repo_errors.append({"url": candidate_url, "error_type": "network", "message": str(e)})

    if repo_errors:
        mp.repo_errors = repo_errors

    logger.info("Maven enrichment completed", extra=extra_context(
        event="complete", component="enrich", action="enrich_with_repo",
        outcome="success", count=len(candidates), duration_ms=t.duration_ms(),
        package_manager="maven"
    ))

    if is_debug_enabled(logger):
        logger.debug("Maven enrichment finished", extra=extra_context(
            event="function_exit", component="enrich", action="enrich_with_repo",
            outcome="success", count=len(candidates), duration_ms=t.duration_ms(),
            package_manager="maven"
        ))
