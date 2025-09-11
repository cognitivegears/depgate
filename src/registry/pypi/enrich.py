"""PyPI enrichment: RTD resolution, repository discovery, validation, and version matching."""
from __future__ import annotations

import importlib
import logging
from typing import Any, Dict, List, Optional

from common.logging_utils import extra_context, is_debug_enabled, Timer
from repository.providers import ProviderType, map_host_to_type
from repository.provider_registry import ProviderRegistry
from repository.provider_validation import ProviderValidationService
from registry.depsdev.enrich import enrich_metapackage as depsdev_enrich

from .discovery import _extract_repo_candidates

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

# Expose as module attribute for tests to patch like registry.pypi.enrich.pypi_pkg.normalize_repo_url
pypi_pkg = _PkgAccessor('registry.pypi')

def _extract_license_from_info(info: Dict[str, Any]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract license information from PyPI info metadata.

    Returns:
        (license_id, license_source, license_url)
    """
    classifiers = info.get("classifiers", []) or []
    license_id: Optional[str] = None
    license_source: Optional[str] = None
    license_url: Optional[str] = None

    def _map_classifier(text: str) -> Optional[str]:
        s = str(text).lower()
        if "license ::" not in s:
            return None
        mapping = {
            "mit license": "MIT",
            "apache software license": "Apache-2.0",
            "bsd license": "BSD-3-Clause",
            "isc license": "ISC",
            "mozilla public license 2.0": "MPL-2.0",
            "gnu general public license v2": "GPL-2.0-only",
            "gnu general public license v3": "GPL-3.0-only",
            "gnu lesser general public license v2.1": "LGPL-2.1-only",
            "gnu lesser general public license v3": "LGPL-3.0-only",
        }
        for key, spdx in mapping.items():
            if key in s:
                return spdx
        return None

    # Prefer Trove classifiers
    for c in classifiers:
        mapped = _map_classifier(c)
        if mapped:
            license_id = mapped
            license_source = "pypi_classifiers"
            break

    # Fallback: info.license free text
    if license_id is None:
        raw = str(info.get("license") or "").strip()
        if raw:
            rl = raw.lower()
            if raw.upper() == "MIT" or "mit" in rl:
                license_id = "MIT"
            elif "apache" in rl and ("2.0" in rl or "2" in rl):
                license_id = "Apache-2.0"
            elif rl.startswith("bsd") or "bsd license" in rl:
                license_id = "BSD-3-Clause"
            elif rl == "isc" or "isc license" in rl:
                license_id = "ISC"
            elif "mpl" in rl or "mozilla public license" in rl:
                license_id = "MPL-2.0"
            elif "lgpl" in rl and ("2.1" in rl or "2_1" in rl):
                license_id = "LGPL-2.1-only"
            elif "lgpl" in rl and "3" in rl:
                license_id = "LGPL-3.0-only"
            elif "gpl" in rl and "3" in rl:
                license_id = "GPL-3.0-only"
            elif "gpl" in rl and "2" in rl:
                license_id = "GPL-2.0-only"
            if license_id:
                license_source = "pypi_license"

    # Fallback: project_urls License link
    project_urls = info.get("project_urls", {}) or {}
    for key, url in project_urls.items():
        if isinstance(key, str) and isinstance(url, str) and url:
            if "license" in key.lower() or "licence" in key.lower():
                license_url = url
                if license_source is None and license_id is None:
                    license_source = "pypi_project_urls"
                break

    return license_id, license_source, license_url


def _enrich_with_license(mp, info: Dict[str, Any]) -> None:
    """Populate MetaPackage license fields from PyPI info metadata."""
    lic_id, lic_source, lic_url = _extract_license_from_info(info)
    if lic_id or lic_url:
        setattr(mp, "license_id", lic_id)
        setattr(mp, "license_source", lic_source)
        setattr(mp, "license_available", True)
        if lic_url:
            setattr(mp, "license_url", lic_url)

def _resolve_pypi_candidate(candidate_url: str, provenance: Dict[str, Any]) -> tuple[str, Dict[str, Any]]:
    """Resolve a candidate URL, attempting RTD resolution when applicable; returns (final_url, provenance)."""
    final_url = candidate_url
    if ("readthedocs.io" in candidate_url) or ("readthedocs.org" in candidate_url):
        if is_debug_enabled(logger):
            logger.debug("Attempting RTD resolution for docs URL", extra=extra_context(
                event="decision", component="enrich", action="try_rtd_resolution",
                target="rtd_url", outcome="attempting", package_manager="pypi"
            ))
        rtd_repo_url = pypi_pkg._maybe_resolve_via_rtd(candidate_url)  # type: ignore[attr-defined]  # pylint: disable=protected-access
        if rtd_repo_url:
            final_url = rtd_repo_url
            provenance = dict(provenance)
            provenance["rtd_slug"] = pypi_pkg.infer_rtd_slug(candidate_url)
            provenance["rtd_source"] = "detail"
            if is_debug_enabled(logger):
                logger.debug("RTD resolution successful", extra=extra_context(
                    event="decision", component="enrich", action="try_rtd_resolution",
                    target="rtd_url", outcome="resolved", package_manager="pypi"
                ))
        else:
            if is_debug_enabled(logger):
                logger.debug("RTD resolution failed, using original URL", extra=extra_context(
                    event="decision", component="enrich", action="try_rtd_resolution",
                    target="rtd_url", outcome="failed", package_manager="pypi"
                ))
    return final_url, provenance


def _version_for_match(mp, fallback_version: str) -> str:
    """Compute version used for repo version match with exact-unsatisfiable guard."""
    mode = str(getattr(mp, "resolution_mode", "")).lower()
    if mode == "exact" and getattr(mp, "resolved_version", None) is None:
        return ""
    return getattr(mp, "resolved_version", None) or fallback_version


def _provider_for_host(host: str):
    """Create a provider instance for a normalized host or return None if unknown."""
    ptype = map_host_to_type(host)
    if ptype == ProviderType.UNKNOWN:
        return None
    injected = (
        {"github": pypi_pkg.GitHubClient()}
        if ptype == ProviderType.GITHUB
        else {"gitlab": pypi_pkg.GitLabClient()}
    )
    # ProviderRegistry returns a ProviderClient compatible object
    return ProviderRegistry.get(ptype, injected)  # type: ignore

def _maybe_resolve_via_rtd(url: str) -> Optional[str]:
    """Resolve repository URL from Read the Docs URL if applicable.

    Args:
        url: Potential RTD URL

    Returns:
        Repository URL if RTD resolution succeeds, None otherwise
    """
    if not url:
        return None

    # Use package namespace via lazy accessor (registry.pypi.*), provided by pypi_pkg above

    slug = pypi_pkg.infer_rtd_slug(url)
    if slug:
        if is_debug_enabled(logger):
            logger.debug("RTD slug inferred, attempting resolution", extra=extra_context(
                event="decision", component="enrich", action="maybe_resolve_via_rtd",
                target="rtd_url", outcome="slug_found", package_manager="pypi"
            ))
        repo_url = pypi_pkg.resolve_repo_from_rtd(url)
        if repo_url:
            if is_debug_enabled(logger):
                logger.debug("RTD resolution successful", extra=extra_context(
                    event="function_exit", component="enrich", action="maybe_resolve_via_rtd",
                    outcome="resolved", package_manager="pypi"
                ))
            return repo_url
        if is_debug_enabled(logger):
            logger.debug("RTD resolution failed", extra=extra_context(
                event="function_exit", component="enrich", action="maybe_resolve_via_rtd",
                outcome="resolution_failed", package_manager="pypi"
            ))
    else:
        if is_debug_enabled(logger):
            logger.debug("No RTD slug found", extra=extra_context(
                event="function_exit", component="enrich", action="maybe_resolve_via_rtd",
                outcome="no_slug", package_manager="pypi"
            ))

    return None


def _enrich_with_repo(mp, _name: str, info: Dict[str, Any], version: str) -> None:
    """Enrich MetaPackage with repository discovery, validation, and version matching.

    Args:
        mp: MetaPackage instance to update
        name: Package name
        info: PyPI package info dict
        version: Package version string
    """
    with Timer() as t:
        if is_debug_enabled(logger):
            logger.debug("Starting PyPI enrichment", extra=extra_context(
                event="function_entry", component="enrich", action="enrich_with_repo",
                package_manager="pypi"
            ))
        # Milestone start
        logger.info("PyPI enrichment started", extra=extra_context(
            event="start", component="enrich", action="enrich_with_repo",
            package_manager="pypi"
        ))

        candidates = _extract_repo_candidates(info)
        mp.repo_present_in_registry = bool(candidates)

    provenance: Dict[str, Any] = {}
    repo_errors: List[Dict[str, Any]] = []

    # Access patchable symbols via package for test monkeypatching (lazy accessor pypi_pkg)

    # Try each candidate URL
    for candidate_url in candidates:
        # Resolve candidate (handles RTD URLs)
        final_url, provenance = _resolve_pypi_candidate(candidate_url, provenance)

        # Normalize the URL
        normalized = pypi_pkg.normalize_repo_url(final_url)
        if not normalized:
            continue

        # Update provenance
        if "rtd_slug" not in provenance:
            provenance["pypi_project_urls"] = final_url
        if final_url != normalized.normalized_url:
            provenance["normalization_changed"] = True

        # Set normalized URL and host
        mp.repo_url_normalized = normalized.normalized_url
        mp.repo_host = normalized.host
        mp.provenance = provenance

        # Compute version used for repository version matching (with exact guard)
        version_for_match = _version_for_match(mp, version)
        # Mark one-shot decay for repo_resolved when exact-unsatisfiable (empty version_for_match)
        if version_for_match == "":
            setattr(mp, "_unsat_exact_decay", True)

        # Validate with provider client
        try:
            provider = _provider_for_host(normalized.host)
            if provider:
                ProviderValidationService.validate_and_populate(
                    mp, normalized, version_for_match, provider, pypi_pkg.VersionMatcher()
                )
            if mp.repo_exists:
                mp.repo_resolved = True
                break  # Found a valid repo, stop trying candidates

        except Exception as e:  # pylint: disable=broad-except
            # Record error but continue
            repo_errors.append(
                {"url": final_url, "error_type": "network", "message": str(e)}
            )

    if repo_errors:
        mp.repo_errors = repo_errors

    # deps.dev enrichment (backfill-only; feature flag enforced inside function)
    try:
        deps_version = getattr(mp, "resolved_version", None) or version
        depsdev_enrich(mp, "pypi", getattr(mp, "pkg_name", None) or "", deps_version)
    except Exception:
        # Defensive: never fail PyPI enrichment due to deps.dev issues
        pass

    logger.info("PyPI enrichment completed", extra=extra_context(
        event="complete", component="enrich", action="enrich_with_repo",
        outcome="success", count=len(candidates), duration_ms=t.duration_ms(),
        package_manager="pypi"
    ))

    if is_debug_enabled(logger):
        logger.debug("PyPI enrichment finished", extra=extra_context(
            event="function_exit", component="enrich", action="enrich_with_repo",
            outcome="success", count=len(candidates), duration_ms=t.duration_ms(),
            package_manager="pypi"
        ))
