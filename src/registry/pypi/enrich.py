"""PyPI enrichment: RTD resolution, repository discovery, validation, and version matching."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from common.logging_utils import extra_context, is_debug_enabled, Timer
from repository.providers import ProviderType, map_host_to_type
from repository.provider_registry import ProviderRegistry
from repository.provider_validation import ProviderValidationService

from .discovery import _extract_repo_candidates

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

# Expose as module attribute for tests to patch like registry.pypi.enrich.pypi_pkg.normalize_repo_url
pypi_pkg = _PkgAccessor('registry.pypi')


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
        else:
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


def _enrich_with_repo(mp, name: str, info: Dict[str, Any], version: str) -> None:
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
        # Only try RTD resolution for RTD-hosted docs URLs
        if ("readthedocs.io" in candidate_url) or ("readthedocs.org" in candidate_url):
            if is_debug_enabled(logger):
                logger.debug("Attempting RTD resolution for docs URL", extra=extra_context(
                    event="decision", component="enrich", action="try_rtd_resolution",
                    target="rtd_url", outcome="attempting", package_manager="pypi"
                ))
            rtd_repo_url = pypi_pkg._maybe_resolve_via_rtd(candidate_url)  # type: ignore[attr-defined]
            if rtd_repo_url:
                final_url = rtd_repo_url
                provenance["rtd_slug"] = pypi_pkg.infer_rtd_slug(candidate_url)
                provenance["rtd_source"] = "detail"  # Simplified
                if is_debug_enabled(logger):
                    logger.debug("RTD resolution successful", extra=extra_context(
                        event="decision", component="enrich", action="try_rtd_resolution",
                        target="rtd_url", outcome="resolved", package_manager="pypi"
                    ))
            else:
                final_url = candidate_url
                if is_debug_enabled(logger):
                    logger.debug("RTD resolution failed, using original URL", extra=extra_context(
                        event="decision", component="enrich", action="try_rtd_resolution",
                        target="rtd_url", outcome="failed", package_manager="pypi"
                    ))
        else:
            final_url = candidate_url

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

        # Validate with provider client
        try:
            ptype = map_host_to_type(normalized.host)
            if ptype != ProviderType.UNKNOWN:
                injected = (
                    {"github": pypi_pkg.GitHubClient()}
                    if ptype == ProviderType.GITHUB
                    else {"gitlab": pypi_pkg.GitLabClient()}
                )
                provider = ProviderRegistry.get(ptype, injected)  # type: ignore
                ProviderValidationService.validate_and_populate(
                    mp, normalized, version, provider, pypi_pkg.VersionMatcher()
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
