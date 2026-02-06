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
                'default_branch': data.get('default_branch'),
                'forks_count': data.get('forks_count'),
                'open_issues_count': data.get('open_issues_count'),
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

    def get_open_prs_count(self, owner: str, repo: str) -> Optional[int]:
        """Get open merge request count for project.

        Args:
            owner: Project owner/namespace
            repo: Project name

        Returns:
            Open MR count or None on error
        """
        project_path = quote(f"{owner}/{repo}", safe='')
        url = f"{self.base_url}/projects/{project_path}/merge_requests?state=opened&per_page=1"
        return self._get_paginated_count(url)

    def get_last_commit(self, owner: str, repo: str) -> Optional[str]:
        """Get last commit timestamp for project.

        Args:
            owner: Project owner/namespace
            repo: Project name

        Returns:
            ISO 8601 timestamp or None on error
        """
        project_path = quote(f"{owner}/{repo}", safe='')
        url = f"{self.base_url}/projects/{project_path}/repository/commits?per_page=1"
        status, _, data = get_json(url, headers=self._get_headers())
        if status == 200 and data:
            first = data[0] if isinstance(data[0], dict) else {}
            return first.get("committed_date") or first.get("created_at")
        return None

    def get_last_merged_pr(self, owner: str, repo: str) -> Optional[str]:
        """Get last merged merge request timestamp.

        Args:
            owner: Project owner/namespace
            repo: Project name

        Returns:
            ISO 8601 timestamp or None on error
        """
        project_path = quote(f"{owner}/{repo}", safe='')
        url = (
            f"{self.base_url}/projects/{project_path}/merge_requests"
            "?state=merged&order_by=updated_at&sort=desc&per_page=10"
        )
        status, _, data = get_json(url, headers=self._get_headers())
        if status == 200 and data:
            for mr in data:
                if isinstance(mr, dict) and mr.get("merged_at"):
                    return mr.get("merged_at")
        return None

    def get_last_closed_issue(self, owner: str, repo: str) -> Optional[str]:
        """Get last closed issue timestamp.

        Args:
            owner: Project owner/namespace
            repo: Project name

        Returns:
            ISO 8601 timestamp or None on error
        """
        project_path = quote(f"{owner}/{repo}", safe='')
        url = (
            f"{self.base_url}/projects/{project_path}/issues"
            "?state=closed&order_by=updated_at&sort=desc&per_page=10"
        )
        status, _, data = get_json(url, headers=self._get_headers())
        if status == 200 and data:
            for issue in data:
                if isinstance(issue, dict):
                    return issue.get("closed_at")
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

    def _get_paginated_count(self, url: str) -> Optional[int]:
        """Get a total count from a paginated endpoint."""
        status, headers, data = get_json(url, headers=self._get_headers())
        if status == 200:
            total = headers.get('x-total')
            if total:
                try:
                    return int(total)
                except ValueError:
                    pass
            if data is not None:
                return len(data)
        return None

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
