"""URL normalization utilities for repository URLs.

Provides utilities to normalize various git URL formats to a standard
https://host/owner/repo format, with support for detecting host types
and extracting repository information.
"""
from __future__ import annotations

import re
from typing import Optional
from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass
class RepoRef:
    """Data object representing a normalized repository reference.

    Attributes:
        normalized_url: The normalized HTTPS URL (e.g., "https://github.com/owner/repo")
        host: Host type ("github", "gitlab", or "other")
        owner: Repository owner/organization name
        repo: Repository name (without .git suffix)
        directory: Optional monorepo directory hint
    """
    normalized_url: str
    host: str
    owner: str
    repo: str
    directory: Optional[str] = None


def normalize_repo_url(url: Optional[str], directory: Optional[str] = None) -> Optional[RepoRef]:
    """Normalize any git URL to standard https://host/owner/repo format.

    Handles various git URL formats:
    - git+https://host/owner/repo(.git)
    - git://host/owner/repo(.git)
    - ssh://git@host/owner/repo(.git)
    - git@host:owner/repo(.git)
    - https://host/owner/repo(.git)

    Args:
        url: The git URL to normalize
        directory: Optional monorepo directory hint

    Returns:
        RepoRef object with normalized information, or None if URL cannot be parsed
    """
    if not url:
        return None

    # Clean the URL
    url = url.strip()

    # Remove git+ prefix
    if url.startswith('git+'):
        url = url[4:]

    # Handle SSH-style URLs: git@host:owner/repo
    ssh_pattern = r'^git@([^:]+):(.+)/([^/]+?)(\.git)?/?$'
    match = re.match(ssh_pattern, url)
    if match:
        host, owner, repo, _ = match.groups()
        return _create_repo_ref(host, owner, repo, directory)

    # Handle SSH protocol: ssh://git@host/owner/repo
    ssh_proto_pattern = r'^ssh://git@([^/]+)/(.+)/([^/]+?)(\.git)?/?$'
    match = re.match(ssh_proto_pattern, url)
    if match:
        host, owner, repo, _ = match.groups()
        return _create_repo_ref(host, owner, repo, directory)

    # Handle HTTPS/HTTP URLs
    parsed = _parse_http_repo_url(url)
    if parsed:
        host, owner, repo = parsed
        return _create_repo_ref(host, owner, repo, directory)

    # Handle git:// protocol
    git_pattern = r'^git://([^/]+)/(.+)/([^/]+?)(\.git)?/?$'
    match = re.match(git_pattern, url)
    if match:
        host, owner, repo, _ = match.groups()
        return _create_repo_ref(host, owner, repo, directory)

    return None


def _create_repo_ref(host: str, owner: str, repo: str, directory: Optional[str]) -> RepoRef:
    """Create a RepoRef object with normalized URL and detected host type.

    Args:
        host: The host domain
        owner: Repository owner
        repo: Repository name
        directory: Optional directory hint

    Returns:
        RepoRef object
    """
    # Normalize host to lowercase
    host = host.lower()
    owner = owner.strip("/")
    repo = repo.strip("/")
    if repo.endswith(".git"):
        repo = repo[:-4]

    # Detect host type
    if 'github.com' in host:
        host_type = 'github'
    elif 'gitlab.com' in host:
        host_type = 'gitlab'
    else:
        host_type = 'other'

    # Construct normalized URL
    normalized_url = f'https://{host}/{owner}/{repo}'

    return RepoRef(
        normalized_url=normalized_url,
        host=host_type,
        owner=owner,
        repo=repo,
        directory=directory
    )


def _parse_http_repo_url(url: str) -> Optional[tuple[str, str, str]]:
    """Parse HTTP(S) repository URLs, trimming known non-repo path suffixes."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return None

    host = parsed.netloc.lower()
    segments = [seg for seg in (parsed.path or "").split("/") if seg]
    if len(segments) < 2:
        return None

    # GitHub repositories are always /owner/repo; ignore any trailing resource paths.
    if "github.com" in host:
        return host, segments[0], segments[1]

    # GitLab can have nested groups: /group/subgroup/repo
    if "gitlab.com" in host:
        marker_index = _find_marker_index(segments, {
            "-", "blob", "tree", "issues", "merge_requests", "wikis",
            "commits", "tags", "releases",
        })
        project_segments = segments[:marker_index] if marker_index is not None else segments
        if len(project_segments) < 2:
            return None
        return host, "/".join(project_segments[:-1]), project_segments[-1]

    # Generic host fallback: treat final path segment as repo.
    return host, "/".join(segments[:-1]), segments[-1]


def _find_marker_index(segments: list[str], markers: set[str]) -> Optional[int]:
    """Return first index containing a marker segment, if any."""
    for idx, segment in enumerate(segments):
        if segment in markers:
            return idx
    return None
