"""GitLab API client for repository information.

Provides a lightweight REST client for fetching GitLab repository
information including metadata, tags, releases, and contributor counts.
"""
from __future__ import annotations

import os
from typing import List, Optional, Dict, Any
from urllib.parse import quote

from constants import Constants
from common.http_client import get_json


class GitLabClient:
    """Lightweight REST client for GitLab API operations.

    Supports optional authentication via GITLAB_TOKEN environment variable.
    """

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None):
        """Initialize GitLab client.

        Args:
            base_url: Base URL for GitLab API (defaults to Constants.GITLAB_API_BASE)
            token: GitLab personal access token (defaults to GITLAB_TOKEN env var)
        """
        self.base_url = base_url or Constants.GITLAB_API_BASE
        self.token = token or os.environ.get(Constants.ENV_GITLAB_TOKEN)

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers including authorization if token is available."""
        headers = {}
        if self.token:
            headers['Private-Token'] = self.token
        return headers

    def get_project(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        """Fetch project metadata.

        Args:
            owner: Project owner/namespace
            repo: Project name

        Returns:
            Dict with star_count, last_activity_at, default_branch, or None on error
        """
        # URL encode the project path
        project_path = quote(f"{owner}/{repo}", safe='')
        url = f"{self.base_url}/projects/{project_path}"

        status, _, data = get_json(url, headers=self._get_headers())

        if status == 200 and data:
            return {
                'star_count': data.get('star_count'),
                'last_activity_at': data.get('last_activity_at'),
                'default_branch': data.get('default_branch')
            }
        return None

    def get_tags(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        """Fetch project tags with pagination.

        Args:
            owner: Project owner/namespace
            repo: Project name

        Returns:
            List of tag dictionaries
        """
        project_path = quote(f"{owner}/{repo}", safe='')
        return self._get_paginated_results(
            f"{self.base_url}/projects/{project_path}/repository/tags"
        )

    def get_releases(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        """Fetch project releases with pagination.

        Args:
            owner: Project owner/namespace
            repo: Project name

        Returns:
            List of release dictionaries
        """
        project_path = quote(f"{owner}/{repo}", safe='')
        return self._get_paginated_results(
            f"{self.base_url}/projects/{project_path}/releases"
        )

    def get_contributors_count(self, owner: str, repo: str) -> Optional[int]:
        """Get contributor count for project.

        Note: GitLab contributor statistics may be inaccurate on very large repos
        due to API limitations.

        Args:
            owner: Project owner/namespace
            repo: Project name

        Returns:
            Contributor count or None on error
        """
        project_path = quote(f"{owner}/{repo}", safe='')
        url = f"{self.base_url}/projects/{project_path}/repository/contributors"

        status, _, data = get_json(url, headers=self._get_headers())

        if status == 200 and data:
            return len(data)

        return None

    def _get_paginated_results(self, url: str) -> List[Dict[str, Any]]:
        """Fetch all pages of a paginated endpoint.

        Args:
            url: Base URL for paginated endpoint

        Returns:
            List of all results across pages
        """
        results = []
        current_url = f"{url}?per_page={Constants.REPO_API_PER_PAGE}"

        while current_url:
            status, headers, data = get_json(current_url, headers=self._get_headers())

            if status != 200 or not data:
                break

            results.extend(data)

            # Check for next page
            current_page = self._get_current_page(headers)
            total_pages = self._get_total_pages(headers)

            if current_page and total_pages and current_page < total_pages:
                next_page = current_page + 1
                current_url = f"{url}?per_page={Constants.REPO_API_PER_PAGE}&page={next_page}"
            else:
                current_url = None

        return results

    def _get_current_page(self, headers: Dict[str, str]) -> Optional[int]:
        """Extract current page from response headers.

        Args:
            headers: Response headers

        Returns:
            Current page number or None
        """
        page_str = headers.get('x-page')
        if page_str:
            try:
                return int(page_str)
            except ValueError:
                pass
        return None

    def _get_total_pages(self, headers: Dict[str, str]) -> Optional[int]:
        """Extract total pages from response headers.

        Args:
            headers: Response headers

        Returns:
            Total pages or None
        """
        total_str = headers.get('x-total-pages')
        if total_str:
            try:
                return int(total_str)
            except ValueError:
                pass
        return None
