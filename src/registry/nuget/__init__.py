"""NuGet registry package.

This package provides NuGet package manager support:
- discovery.py: repository URL and license extraction from nuspec metadata
- enrich.py: repository discovery/validation and version matching
- client.py: HTTP interactions with NuGet V3 API (primary) and V2 API (fallback)
- scan.py: source scanning for .csproj, packages.config, project.json, Directory.Build.props

Public API is preserved at registry.nuget without shims.
"""

# Patch points exposed for tests (e.g., monkeypatch in tests)
from repository.url_normalize import normalize_repo_url  # noqa: F401
from repository.version_match import VersionMatcher  # noqa: F401
from repository.github import GitHubClient  # noqa: F401
from repository.gitlab import GitLabClient  # noqa: F401
from common.http_client import safe_get  # noqa: F401

# Public API re-exports
from .discovery import (  # noqa: F401
    _extract_repo_candidates,
    _extract_license_from_metadata,
)
from .enrich import _enrich_with_repo  # noqa: F401
from .client import recv_pkg_info  # noqa: F401
from .scan import scan_source  # noqa: F401

__all__ = [
    # Helpers
    "_extract_repo_candidates",
    "_extract_license_from_metadata",
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
    "safe_get",
]
