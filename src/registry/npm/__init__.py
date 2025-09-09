"""NPM registry package.

This package splits the former monolithic registry/npm.py into focused modules:
- discovery.py: parsing and candidate extraction helpers
- enrich.py: repository discovery/validation and version matching
- client.py: HTTP interactions with the npm registry
- scan.py: source scanning for package.json

Public API is preserved at registry.npm without shims.
"""

# Patch points exposed for tests (e.g., monkeypatch in tests)
from repository.url_normalize import normalize_repo_url  # noqa: F401
from repository.version_match import VersionMatcher  # noqa: F401
from repository.github import GitHubClient  # noqa: F401
from repository.gitlab import GitLabClient  # noqa: F401
from common.http_client import safe_get, safe_post  # noqa: F401

# Public API re-exports
from .discovery import (  # noqa: F401
    get_keys,
    _extract_latest_version,
    _parse_repository_field,
    _extract_fallback_urls,
)
from .enrich import _enrich_with_repo  # noqa: F401
from .client import get_package_details, recv_pkg_info  # noqa: F401
from .scan import scan_source  # noqa: F401

__all__ = [
    # Helpers
    "get_keys",
    "_extract_latest_version",
    "_parse_repository_field",
    "_extract_fallback_urls",
    # Enrichment
    "_enrich_with_repo",
    # Client/scan
    "get_package_details",
    "recv_pkg_info",
    "scan_source",
    # Patch points for tests
    "VersionMatcher",
    "GitHubClient",
    "GitLabClient",
    "normalize_repo_url",
    "safe_get",
    "safe_post",
]
