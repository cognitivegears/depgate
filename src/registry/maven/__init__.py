"""Maven registry package.

This package splits the former monolithic registry/maven.py into focused modules:
- discovery.py: metadata and POM traversal helpers
- enrich.py: repository discovery/validation and version matching
- client.py: registry search client and source scanner

Public API is preserved at registry.maven without shims.
"""

# Patch points exposed for tests (e.g., monkeypatch in tests)
from repository.url_normalize import normalize_repo_url  # noqa: F401
from repository.version_match import VersionMatcher  # noqa: F401
from repository.github import GitHubClient  # noqa: F401
from repository.gitlab import GitLabClient  # noqa: F401

# Public API re-exports
from .discovery import (  # noqa: F401
    _resolve_latest_version,
    _artifact_pom_url,
    _fetch_pom,
    _parse_scm_from_pom,
    _normalize_scm_to_repo_url,
    _traverse_for_scm,
    _url_fallback_from_pom,
)
from .enrich import _enrich_with_repo  # noqa: F401
from .client import recv_pkg_info, scan_source  # noqa: F401

__all__ = [
    # Discovery helpers
    "_resolve_latest_version",
    "_artifact_pom_url",
    "_fetch_pom",
    "_parse_scm_from_pom",
    "_normalize_scm_to_repo_url",
    "_traverse_for_scm",
    "_url_fallback_from_pom",
    # Enrichment
    "_enrich_with_repo",
    # Client/scan
    "recv_pkg_info",
    "scan_source",
    # Patch points for tests
    "VersionMatcher",
    "GitHubClient",
    "GitLabClient",
    "normalize_repo_url",
]
