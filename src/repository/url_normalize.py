"""URL normalization utilities for repository URLs.

Provides utilities to normalize various git URL formats to a standard
https://host/owner/repo format, with support for detecting host types
and extracting repository information.
"""
from __future__ import annotations

import re
from typing import Optional
from dataclasses import dataclass


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
    https_pattern = r'^https?://([^/]+)/(.+)/([^/]+?)(\.git)?/?$'
    match = re.match(https_pattern, url)
    if match:
        host, owner, repo, _ = match.groups()
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
