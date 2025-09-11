"""Maven enrichment: repository discovery, validation, and version matching."""
from __future__ import annotations

import importlib
import logging
from typing import Any, Dict, List, Optional, Tuple

from common.logging_utils import extra_context, is_debug_enabled, Timer
from repository.providers import ProviderType, map_host_to_type
from repository.provider_registry import ProviderRegistry
from repository.provider_validation import ProviderValidationService
from registry.depsdev.enrich import enrich_metapackage as depsdev_enrich

from .discovery import (
    _normalize_scm_to_repo_url,
    _fetch_pom,
    _url_fallback_from_pom,
    _parse_license_from_pom,
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

# Expose as module attribute for tests to patch like registry.maven.enrich.maven_pkg.normalize_repo_url
maven_pkg = _PkgAccessor('registry.maven')

def _provider_for_host(host: str):
    """Create a provider instance for a normalized host or return None if unknown."""
    ptype = map_host_to_type(host)
    if ptype == ProviderType.UNKNOWN:
        return None
    injected = (
        {"github": maven_pkg.GitHubClient()}
        if ptype == ProviderType.GITHUB
        else {"gitlab": maven_pkg.GitLabClient()}
    )
    # ProviderRegistry returns a ProviderClient compatible object
    return ProviderRegistry.get(ptype, injected)  # type: ignore


def _version_for_match(mp, fallback_version: Optional[str]) -> str:
    """Compute version used for repo version match with exact-unsatisfiable guard."""
    mode = str(getattr(mp, "resolution_mode", "")).lower()
    if mode == "exact" and getattr(mp, "resolved_version", None) is None:
        return ""
    return getattr(mp, "resolved_version", None) or (fallback_version or "")


def _build_candidates_and_provenance(
    group: str,
    artifact: str,
    version: str,
    provenance: Dict[str, Any],
    mp,
) -> Tuple[List[str], Dict[str, Any]]:
    """Build candidate repository URLs from SCM traversal and fallback POM & update provenance."""
    # Try to get SCM from POM traversal
    if is_debug_enabled(logger):
        logger.debug(
            "Starting SCM traversal for Maven POM",
            extra=extra_context(
                event="function_entry",
                component="enrich",
                action="traverse_for_scm",
                package_manager="maven",
            ),
        )
    scm_info = maven_pkg._traverse_for_scm(group, artifact, version, provenance)  # pylint: disable=protected-access
    # Allow _traverse_for_scm to return either a plain SCM dict or a wrapper with keys
    # 'scm' (dict) and optional 'provenance' (dict) for additional context.
    if isinstance(scm_info, dict) and "provenance" in scm_info and isinstance(scm_info["provenance"], dict):
        # Merge any provenance supplied by traversal
        provenance = {**provenance, **scm_info["provenance"]}
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
                logger.debug(
                    "Using SCM URL from POM traversal",
                    extra=extra_context(
                        event="decision",
                        component="enrich",
                        action="choose_candidate",
                        target="scm",
                        outcome="primary",
                        package_manager="maven",
                    ),
                )

    # Fallback: <url> field from POM
    if not candidates:
        if is_debug_enabled(logger):
            logger.debug(
                "No SCM found, trying URL fallback from POM",
                extra=extra_context(
                    event="decision",
                    component="enrich",
                    action="choose_candidate",
                    target="url_fallback",
                    outcome="attempting",
                    package_manager="maven",
                ),
            )
        pom_xml = _fetch_pom(group, artifact, version)
        if pom_xml:
            fallback_url = _url_fallback_from_pom(pom_xml)
            if fallback_url:
                candidates.append(fallback_url)
                mp.repo_present_in_registry = True
                provenance["maven_pom.url_fallback"] = fallback_url
                if is_debug_enabled(logger):
                    logger.debug(
                        "Using URL fallback from POM",
                        extra=extra_context(
                            event="decision",
                            component="enrich",
                            action="choose_candidate",
                            target="url_fallback",
                            outcome="fallback_used",
                            package_manager="maven",
                        ),
                    )
    return candidates, provenance

def _finalize_candidate(mp, normalized: Any, provenance: Dict[str, Any]) -> None:
    """Set normalized URL/host and propagate provenance to the MetaPackage."""
    mp.repo_url_normalized = normalized.normalized_url
    mp.repo_host = normalized.host
    mp.provenance = provenance

def _enrich_with_repo(mp, group: str, artifact: str, version: Optional[str]) -> None:  # pylint: disable=too-many-branches
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
        # pylint: disable=protected-access
        if not version:
            version = maven_pkg._resolve_latest_version(group, artifact)
            if version:
                provenance = mp.provenance or {}
                provenance["maven_metadata.release"] = version
                mp.provenance = provenance
                # Expose resolved version so downstream enrichment (deps.dev) can use it
                try:
                    setattr(mp, "resolved_version", version)
                except Exception:  # pylint: disable=broad-exception-caught
                    pass
                if is_debug_enabled(logger):
                    logger.debug(
                        "Resolved latest version from Maven metadata",
                        extra=extra_context(
                            event="decision",
                            component="enrich",
                            action="resolve_version",
                            target="maven-metadata.xml",
                            outcome="resolved",
                            package_manager="maven",
                        ),
                    )
        # pylint: enable=protected-access

        if not version:
            if is_debug_enabled(logger):
                logger.debug("No version available for Maven enrichment", extra=extra_context(
                    event="function_exit", component="enrich", action="enrich_with_repo",
                    outcome="no_version", package_manager="maven", duration_ms=t.duration_ms()
                ))
            return

    provenance: Dict[str, Any] = mp.provenance or {}
    repo_errors: List[Dict[str, Any]] = []

    candidates, provenance = _build_candidates_and_provenance(
        group, artifact, version, provenance, mp
    )

    # Try each candidate URL
    for candidate_url in candidates:
        # Normalize the URL (use package-level for test monkeypatching)
        normalized = maven_pkg.normalize_repo_url(candidate_url)
        if not normalized:
            continue

        # Set normalized URL and host
        _finalize_candidate(mp, normalized, provenance)

        # Validate with provider client
        try:
            provider = _provider_for_host(normalized.host)
            if provider:
                ProviderValidationService.validate_and_populate(
                    mp, normalized, _version_for_match(mp, version), provider, maven_pkg.VersionMatcher()
                )
            if mp.repo_exists:
                mp.repo_resolved = True
                break  # Found a valid repo, stop trying candidates

        except Exception as e:  # pylint: disable=broad-except
            # Record error but continue
            repo_errors.append({"url": candidate_url, "error_type": "network", "message": str(e)})

    if repo_errors:
        mp.repo_errors = repo_errors

    # deps.dev enrichment (backfill-only; feature flag enforced inside function)
    try:
        deps_name = f"{group}:{artifact}"
        deps_version = getattr(mp, "resolved_version", None) or version
        depsdev_enrich(mp, "maven", deps_name, deps_version)
    except Exception:
        # Defensive: never fail Maven enrichment due to deps.dev issues
        pass

    # Fallback: parse license from POM if still missing after deps.dev
    try:
        lic_present = getattr(mp, "license_id", None)
        if not isinstance(lic_present, str) or not lic_present.strip():
            pom_xml = _fetch_pom(group, artifact, version)
            if pom_xml:
                lic = _parse_license_from_pom(pom_xml)
                lic_name = ""
                lic_url = ""
                if isinstance(lic, dict):
                    if isinstance(lic.get("name"), str):
                        lic_name = lic.get("name", "").strip()
                    if isinstance(lic.get("url"), str):
                        lic_url = lic.get("url", "").strip()
                if lic_name or lic_url:
                    if lic_name:
                        setattr(mp, "license_id", lic_name)
                    setattr(mp, "license_source", "maven_pom")
                    setattr(mp, "license_available", True)
                    try:
                        setattr(mp, "is_license_available", True)
                    except Exception:  # pylint: disable=broad-exception-caught
                        pass
                    # Record in provenance
                    prov = getattr(mp, "provenance", None) or {}
                    pom_prov = prov.get("maven_pom", {})
                    if not isinstance(pom_prov, dict):
                        pom_prov = {}
                    pom_prov["license"] = {"name": lic_name or None, "url": lic_url or None}
                    prov["maven_pom"] = pom_prov
                    mp.provenance = prov
    except Exception:  # pylint: disable=broad-exception-caught
        # Never fail enrichment if license parsing fails
        pass

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
