"""PyPI discovery helpers split from the former monolithic registry/pypi.py."""
from __future__ import annotations

import logging
from typing import Dict, List

from common.logging_utils import extra_context, is_debug_enabled

logger = logging.getLogger(__name__)


def _extract_repo_candidates(info: Dict) -> List[str]:
    """Extract repository candidate URLs from PyPI package info.

    Returns ordered list of candidate URLs from project_urls and home_page.
    Prefers explicit repository/source keys first, then docs/homepage.

    Args:
        info: PyPI package info dict

    Returns:
        List of candidate URLs in priority order
    """
    if is_debug_enabled(logger):
        logger.debug("Extracting PyPI repository candidates", extra=extra_context(
            event="function_entry", component="discovery", action="extract_repo_candidates",
            package_manager="pypi"
        ))
    candidates: List[str] = []
    project_urls = info.get("project_urls", {}) or {}

    # Priority 1: Explicit repository/source keys in project_urls
    repo_keys = [
        "repository",
        "source",
        "source code",
        "code",
        "project-urls.repository",
        "project-urls.source",
    ]
    repo_candidates = [
        url
        for key, url in project_urls.items()
        if url and any(repo_key.lower() in key.lower() for repo_key in repo_keys)
    ]

    # If repo links exist, include them and any explicit documentation/docs links (but not homepage)
    if repo_candidates:
        if is_debug_enabled(logger):
            logger.debug("Found explicit repository URLs in project_urls", extra=extra_context(
                event="decision", component="discovery", action="extract_repo_candidates",
                target="project_urls", outcome="explicit_repo_found", count=len(repo_candidates),
                package_manager="pypi"
            ))
        doc_keys_strict = ["documentation", "docs"]
        doc_candidates = [
            url
            for key, url in project_urls.items()
            if url and any(doc_key.lower() in key.lower() for doc_key in doc_keys_strict)
        ]
        result = repo_candidates + doc_candidates
        if is_debug_enabled(logger):
            logger.debug("Extracted repository candidates with docs", extra=extra_context(
                event="function_exit", component="discovery", action="extract_repo_candidates",
                count=len(result), package_manager="pypi"
            ))
        return result

    # Priority 2: Documentation/homepage keys that might point to repos (when no explicit repo present)
    doc_keys = ["documentation", "docs", "homepage", "home page"]
    for key, url in project_urls.items():
        if url and any(doc_key.lower() in key.lower() for doc_key in doc_keys):
            candidates.append(url)
            if is_debug_enabled(logger):
                logger.debug("Using documentation/homepage URL as fallback", extra=extra_context(
                    event="decision", component="discovery", action="extract_repo_candidates",
                    target="project_urls", outcome="fallback_docs", package_manager="pypi"
                ))

    # Priority 3: info.home_page as weak fallback
    home_page = info.get("home_page")
    if home_page:
        candidates.append(home_page)
        if is_debug_enabled(logger):
            logger.debug("Using home_page as weak fallback", extra=extra_context(
                event="decision", component="discovery", action="extract_repo_candidates",
                target="home_page", outcome="weak_fallback", package_manager="pypi"
            ))

    if is_debug_enabled(logger):
        logger.debug("Extracted fallback repository candidates", extra=extra_context(
            event="function_exit", component="discovery", action="extract_repo_candidates",
            count=len(candidates), package_manager="pypi"
        ))

    return candidates
