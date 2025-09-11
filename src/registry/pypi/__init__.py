"""PyPI registry package.

This package splits the former monolithic registry/pypi.py into focused modules:
- discovery.py: candidate extraction helpers (_extract_repo_candidates)
- enrich.py: RTD resolution and repository enrichment (_maybe_resolve_via_rtd, _enrich_with_repo)
- client.py: HTTP interactions with the PyPI registry (recv_pkg_info)
- scan.py: source scanning for requirements.txt (scan_source)

Public API is preserved at registry.pypi without shims.
"""

# Patch points exposed for tests (e.g., monkeypatch in tests)
from repository.url_normalize import normalize_repo_url  # noqa: F401
from repository.version_match import VersionMatcher  # noqa: F401
from repository.github import GitHubClient  # noqa: F401
from repository.gitlab import GitLabClient  # noqa: F401
from repository.rtd import infer_rtd_slug, resolve_repo_from_rtd  # noqa: F401
from common.http_client import safe_get  # noqa: F401

# Public API re-exports
from .discovery import _extract_repo_candidates  # noqa: F401
from .enrich import _maybe_resolve_via_rtd, _enrich_with_repo, _enrich_with_license  # noqa: F401
from .client import recv_pkg_info  # noqa: F401
from .scan import scan_source  # noqa: F401

__all__ = [
    # Helpers
    "_extract_repo_candidates",
    "_maybe_resolve_via_rtd",
    # Enrichment
    "_enrich_with_repo",
    "_enrich_with_license",
    # Client/scan
    "recv_pkg_info",
    "scan_source",
    # Patch points for tests
    "VersionMatcher",
    "GitHubClient",
    "GitLabClient",
    "normalize_repo_url",
    "safe_get",
    "infer_rtd_slug",
    "resolve_repo_from_rtd",
]
