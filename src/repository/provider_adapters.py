"""Provider adapter implementations for GitHub and GitLab.

Adapters that implement the ProviderClient interface by wrapping the
existing GitHubClient and GitLabClient classes.
"""
from __future__ import annotations

from typing import Optional, Dict, List

from .providers import ProviderClient
from .github import GitHubClient
from .gitlab import GitLabClient


class GitHubProviderAdapter(ProviderClient):
    """Adapter for GitHub repositories implementing ProviderClient interface."""

    def __init__(self, client: Optional[GitHubClient] = None):
        """Initialize GitHub provider adapter.

        Args:
            client: GitHubClient instance (creates new one if None)
        """
        self.client = client or GitHubClient()

    def provider_name(self) -> str:
        """Return provider name."""
        return 'github'

    def get_repo_info(self, owner: str, repo: str) -> Optional[Dict[str, Optional[str]]]:
        """Fetch repository metadata and normalize to common format.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Dict with normalized keys or None if repository doesn't exist
        """
        repo_data = self.client.get_repo(owner, repo)
        if repo_data:
            return {
                'stars': repo_data.get('stargazers_count'),
                'last_activity_at': repo_data.get('pushed_at')
            }
        return None

    def get_contributors_count(self, owner: str, repo: str) -> Optional[int]:
        """Get contributor count for repository.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Contributor count or None if unavailable
        """
        return self.client.get_contributors_count(owner, repo)

    def get_releases(self, owner: str, repo: str) -> List[Dict[str, str]]:
        """Fetch repository releases for version matching.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            List of release dictionaries. Falls back to tags if releases are empty.
        """
        releases = self.client.get_releases(owner, repo)
        if releases:
            return releases

        # Fallback: use tags when releases are unavailable to enable version matching
        tags = self.client.get_tags(owner, repo)
        return tags or []

    def get_tags(self, owner: str, repo: str) -> List[Dict[str, str]]:
        """Fetch repository tags for version matching."""
        return self.client.get_tags(owner, repo) or []


class GitLabProviderAdapter(ProviderClient):
    """Adapter for GitLab repositories implementing ProviderClient interface."""

    def __init__(self, client: Optional[GitLabClient] = None):
        """Initialize GitLab provider adapter.

        Args:
            client: GitLabClient instance (creates new one if None)
        """
        self.client = client or GitLabClient()

    def provider_name(self) -> str:
        """Return provider name."""
        return 'gitlab'

    def get_repo_info(self, owner: str, repo: str) -> Optional[Dict[str, Optional[str]]]:
        """Fetch project metadata and normalize to common format.

        Args:
            owner: Project owner/namespace
            repo: Project name

        Returns:
            Dict with normalized keys or None if project doesn't exist
        """
        project_data = self.client.get_project(owner, repo)
        if project_data:
            return {
                'stars': project_data.get('star_count'),
                'last_activity_at': project_data.get('last_activity_at')
            }
        return None

    def get_contributors_count(self, owner: str, repo: str) -> Optional[int]:
        """Get contributor count for project.

        Args:
            owner: Project owner/namespace
            repo: Project name

        Returns:
            Contributor count or None if unavailable
        """
        return self.client.get_contributors_count(owner, repo)

    def get_releases(self, owner: str, repo: str) -> List[Dict[str, str]]:
        """Fetch project releases for version matching.

        Args:
            owner: Project owner/namespace
            repo: Project name

        Returns:
            List of release dictionaries. Falls back to tags if releases are empty.
        """
        releases = self.client.get_releases(owner, repo)
        if releases:
            return releases

        # Fallback: use tags when releases are unavailable to enable version matching
        tags = self.client.get_tags(owner, repo)
        return tags or []

    def get_tags(self, owner: str, repo: str) -> List[Dict[str, str]]:
        """Fetch project tags for version matching."""
        return self.client.get_tags(owner, repo) or []
