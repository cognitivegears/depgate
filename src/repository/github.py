"""GitHub API client for repository information.

Provides a lightweight REST client for fetching GitHub repository
information including metadata, tags, releases, and contributor counts.
"""
from __future__ import annotations

import logging
import os
from typing import List, Optional, Dict, Any
from urllib.parse import urlparse, parse_qs, quote

from constants import Constants
from common.http_client import get_json

logger = logging.getLogger(__name__)


class GitHubClient:
    """Lightweight REST client for GitHub API operations.

    Supports optional authentication via GITHUB_TOKEN environment variable.
    """

    def __init__(self, base_url: Optional[str] = None, token: Optional[str] = None):
        """Initialize GitHub client.

        Args:
            base_url: Base URL for GitHub API (defaults to Constants.GITHUB_API_BASE)
            token: GitHub personal access token (defaults to GITHUB_TOKEN env var)
        """
        self.base_url = base_url or Constants.GITHUB_API_BASE
        self.token = token or os.environ.get(Constants.ENV_GITHUB_TOKEN)

    def _get_headers(self) -> Dict[str, str]:
        """Get request headers including authorization if token is available."""
        headers = {'Accept': 'application/vnd.github.v3+json'}
        if self.token:
            headers['Authorization'] = f'token {self.token}'
        return headers

    @staticmethod
    def _get_header_value(headers: Dict[str, Any], key: str) -> str:
        """Read response header value case-insensitively."""
        if not isinstance(headers, dict):
            return ""
        direct = headers.get(key)
        if isinstance(direct, str):
            return direct
        lower_key = key.lower()
        for k, v in headers.items():
            if isinstance(k, str) and k.lower() == lower_key and isinstance(v, str):
                return v
        return ""

    def get_repo(self, owner: str, repo: str) -> Optional[Dict[str, Any]]:
        """Fetch repository metadata.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Dict with stargazers_count, pushed_at, default_branch, or None on error
        """
        url = f"{self.base_url}/repos/{owner}/{repo}"
        status, _, data = get_json(url, headers=self._get_headers())

        if status == 200 and data:
            return {
                'stargazers_count': data.get('stargazers_count'),
                'pushed_at': data.get('pushed_at'),
                'default_branch': data.get('default_branch'),
                'forks_count': data.get('forks_count'),
                'open_issues_count': data.get('open_issues_count'),
            }
        if status in (403, 429):
            logger.warning(
                "GitHub API rate limited (HTTP %s) for %s/%s. "
                "Set GITHUB_TOKEN for higher limits.",
                status, owner, repo
            )
        elif status != 0:  # 0 = already logged by robust_get
            logger.warning(
                "GitHub API returned HTTP %s for %s/%s", status, owner, repo
            )
        return None

    def get_tags(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        """Fetch repository tags with pagination.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            List of tag dictionaries
        """
        return self._get_paginated_results(
            f"{self.base_url}/repos/{owner}/{repo}/tags"
        )

    def get_releases(self, owner: str, repo: str) -> List[Dict[str, Any]]:
        """Fetch repository releases with pagination.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            List of release dictionaries
        """
        return self._get_paginated_results(
            f"{self.base_url}/repos/{owner}/{repo}/releases"
        )

    def get_release_by_tag(self, owner: str, repo: str, tag: str) -> Optional[Dict[str, Any]]:
        """Fetch a single release by exact tag name."""
        if not tag:
            return None
        tag_enc = quote(tag, safe='')
        url = f"{self.base_url}/repos/{owner}/{repo}/releases/tags/{tag_enc}"
        status, _, data = get_json(url, headers=self._get_headers())
        if status == 200 and isinstance(data, dict):
            return data
        if status in (403, 429):
            logger.warning(
                "GitHub API rate limited (HTTP %s) for %s/%s release tag %s. "
                "Set GITHUB_TOKEN for higher limits.",
                status, owner, repo, tag
            )
        elif status not in (0, 404):
            logger.warning(
                "GitHub API returned HTTP %s for %s/%s release tag %s",
                status, owner, repo, tag
            )
        return None

    def get_tag_by_ref(self, owner: str, repo: str, tag: str) -> Optional[Dict[str, Any]]:
        """Fetch a single tag reference by exact tag name."""
        if not tag:
            return None
        tag_enc = quote(tag, safe='')
        url = f"{self.base_url}/repos/{owner}/{repo}/git/ref/tags/{tag_enc}"
        status, _, data = get_json(url, headers=self._get_headers())
        if status == 200 and isinstance(data, dict):
            return {
                "name": tag,
                "ref": data.get("ref"),
                "object": data.get("object"),
            }
        if status in (403, 429):
            logger.warning(
                "GitHub API rate limited (HTTP %s) for %s/%s tag ref %s. "
                "Set GITHUB_TOKEN for higher limits.",
                status, owner, repo, tag
            )
        elif status not in (0, 404):
            logger.warning(
                "GitHub API returned HTTP %s for %s/%s tag ref %s",
                status, owner, repo, tag
            )
        return None

    def find_release_match(
        self, owner: str, repo: str, version: str, matcher: Any
    ) -> Optional[Dict[str, Any]]:
        """Find release match using exact lookups before paginated fallback."""
        if not version:
            return {
                "matched": False,
                "match_type": None,
                "artifact": None,
                "tag_or_release": None,
            }

        for candidate in self._candidate_tag_labels(version):
            release = self.get_release_by_tag(owner, repo, candidate)
            if release:
                result = matcher.find_match(version, [release])
                if result and isinstance(result, dict) and result.get("matched", False):
                    return result

        result = self._find_first_match_in_paginated(
            f"{self.base_url}/repos/{owner}/{repo}/releases",
            version,
            matcher,
        )
        if isinstance(result, dict):
            return result
        return {
            "matched": False,
            "match_type": None,
            "artifact": None,
            "tag_or_release": None,
        }

    def find_tag_match(
        self, owner: str, repo: str, version: str, matcher: Any
    ) -> Optional[Dict[str, Any]]:
        """Find tag match using exact lookups before paginated fallback."""
        if not version:
            return None

        for candidate in self._candidate_tag_labels(version):
            tag_ref = self.get_tag_by_ref(owner, repo, candidate)
            if tag_ref:
                result = matcher.find_match(version, [tag_ref])
                if result and isinstance(result, dict) and result.get("matched", False):
                    return result

        result = self._find_first_match_in_paginated(
            f"{self.base_url}/repos/{owner}/{repo}/tags",
            version,
            matcher,
        )
        if isinstance(result, dict):
            return result
        return {
            "matched": False,
            "match_type": None,
            "artifact": None,
            "tag_or_release": None,
        }

    def get_contributors_count(self, owner: str, repo: str) -> Optional[int]:
        """Get contributor count for repository.

        Uses per_page=1 and Link pagination metadata when available.
        If Link metadata is absent, falls back to the returned page size.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Contributor count or None on error
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/contributors?per_page=1"
        status, headers, data = get_json(url, headers=self._get_headers())

        if status == 200:
            # Try to parse Link header for total count
            link_header = self._get_header_value(headers, 'link')
            if link_header:
                total = self._parse_link_header_total(link_header)
                if total is not None:
                    return total

            # No Link header: treat as single-page response.
            if isinstance(data, list):
                return len(data)
        elif status in (403, 429):
            logger.warning(
                "GitHub API rate limited (HTTP %s) for %s/%s contributors. "
                "Set GITHUB_TOKEN for higher limits.",
                status, owner, repo
            )
        elif status != 0:
            logger.warning(
                "GitHub API returned HTTP %s for %s/%s contributors",
                status, owner, repo
            )
        return None

    def get_open_prs_count(self, owner: str, repo: str) -> Optional[int]:
        """Get open pull request count for repository.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            Open PR count or None on error
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/pulls?state=open&per_page=1"
        return self._get_paginated_count(url)

    def get_last_commit(self, owner: str, repo: str) -> Optional[str]:
        """Get last commit timestamp for repository.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            ISO 8601 timestamp or None on error
        """
        url = f"{self.base_url}/repos/{owner}/{repo}/commits?per_page=1"
        status, _, data = get_json(url, headers=self._get_headers())
        if status == 200 and data:
            commit = data[0].get("commit", {}) if isinstance(data[0], dict) else {}
            committer = commit.get("committer", {}) if isinstance(commit, dict) else {}
            author = commit.get("author", {}) if isinstance(commit, dict) else {}
            return committer.get("date") or author.get("date")
        return None

    def get_last_merged_pr(self, owner: str, repo: str) -> Optional[str]:
        """Get last merged pull request timestamp.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            ISO 8601 timestamp or None on error
        """
        url = (
            f"{self.base_url}/repos/{owner}/{repo}/pulls"
            "?state=closed&sort=updated&direction=desc&per_page=10"
        )
        status, _, data = get_json(url, headers=self._get_headers())
        if status == 200 and data:
            for pr in data:
                if isinstance(pr, dict) and pr.get("merged_at"):
                    return pr.get("merged_at")
        return None

    def get_last_closed_issue(self, owner: str, repo: str) -> Optional[str]:
        """Get last closed issue timestamp.

        Args:
            owner: Repository owner
            repo: Repository name

        Returns:
            ISO 8601 timestamp or None on error
        """
        url = (
            f"{self.base_url}/repos/{owner}/{repo}/issues"
            "?state=closed&sort=updated&direction=desc&per_page=10"
        )
        status, _, data = get_json(url, headers=self._get_headers())
        if status == 200 and data:
            for issue in data:
                if isinstance(issue, dict) and "pull_request" not in issue:
                    return issue.get("closed_at")
        return None

    def _get_paginated_count(self, url: str) -> Optional[int]:
        """Get a total count from a paginated endpoint.

        Args:
            url: Endpoint URL with per_page set.

        Returns:
            Total count or None on error.
        """
        status, headers, data = get_json(url, headers=self._get_headers())
        if status == 200:
            link_header = self._get_header_value(headers, 'link')
            if link_header:
                total = self._parse_link_header_total(link_header)
                if total is not None:
                    return total
            if data is not None:
                return len(data)
        elif status in (403, 429):
            logger.warning(
                "GitHub API rate limited (HTTP %s) for %s. "
                "Set GITHUB_TOKEN for higher limits.",
                status, url
            )
        elif status != 0:
            logger.warning(
                "GitHub API returned HTTP %s for %s", status, url
            )
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
                if status in (403, 429):
                    logger.warning(
                        "GitHub API rate limited (HTTP %s) during pagination for %s. "
                        "Set GITHUB_TOKEN for higher limits.",
                        status, url
                    )
                elif status != 0 and status != 200:
                    logger.warning(
                        "GitHub API returned HTTP %s during pagination for %s",
                        status, url
                    )
                break

            results.extend(data)

            # Check for next page
            link_header = self._get_header_value(headers, 'link')
            current_url = self._get_next_page_url(link_header)

        return results

    def _find_first_match_in_paginated(
        self, url: str, version: str, matcher: Any
    ) -> Optional[Dict[str, Any]]:
        """Scan paginated endpoint page-by-page and stop at first match."""
        current_url = f"{url}?per_page={Constants.REPO_API_PER_PAGE}"

        while current_url:
            status, headers, data = get_json(current_url, headers=self._get_headers())

            if status != 200 or not data:
                if status in (403, 429):
                    logger.warning(
                        "GitHub API rate limited (HTTP %s) during pagination for %s. "
                        "Set GITHUB_TOKEN for higher limits.",
                        status, url
                    )
                elif status != 0 and status != 200:
                    logger.warning(
                        "GitHub API returned HTTP %s during pagination for %s",
                        status, url
                    )
                break

            if isinstance(data, list):
                result = matcher.find_match(version, data)
                if result and isinstance(result, dict) and result.get("matched", False):
                    return result

            link_header = self._get_header_value(headers, 'link')
            current_url = self._get_next_page_url(link_header)

        return None

    def _candidate_tag_labels(self, version: str) -> List[str]:
        """Build exact tag-label candidates for direct endpoint lookups."""
        labels: List[str] = []
        seen = set()

        def _add(candidate: str) -> None:
            c = str(candidate or "").strip()
            if not c or c in seen:
                return
            seen.add(c)
            labels.append(c)

        v = str(version or "").strip()
        if not v:
            return labels

        if v.startswith("v"):
            _add(v)
            _add(v[1:])
        else:
            _add(f"v{v}")
            _add(v)

        return labels

    def _get_next_page_url(self, link_header: str) -> Optional[str]:
        """Extract next page URL from Link header.

        Args:
            link_header: GitHub Link header value

        Returns:
            Next page URL or None if no more pages
        """
        if not link_header:
            return None

        # Parse Link header: <https://api.github.com/...>; rel="next"
        links = link_header.split(',')
        for link in links:
            if 'rel="next"' in link:
                # Extract URL from <url>
                url_match = link.strip().split(';')[0].strip()
                if url_match.startswith('<') and url_match.endswith('>'):
                    return url_match[1:-1]

        return None

    def _parse_link_header_total(self, link_header: str) -> Optional[int]:
        """Parse total count from Link header.

        Args:
            link_header: GitHub Link header value

        Returns:
            Total count or None if unable to parse
        """
        if not link_header:
            return None

        # Look for last page URL and extract page parameter
        links = link_header.split(',')
        for link in links:
            if 'rel="last"' in link:
                url_match = link.strip().split(';')[0].strip()
                if url_match.startswith('<') and url_match.endswith('>'):
                    last_url = url_match[1:-1]
                    parsed = urlparse(last_url)
                    query_params = parse_qs(parsed.query)
                    page = query_params.get('page', [None])[0]
                    if page:
                        try:
                            return int(page)
                        except ValueError:
                            pass

        return None

    def _get_last_page_url(self, link_header: str) -> Optional[str]:
        """Extract last page URL from Link header."""
        if not link_header:
            return None

        links = link_header.split(',')
        for link in links:
            if 'rel="last"' in link:
                url_match = link.strip().split(';')[0].strip()
                if url_match.startswith('<') and url_match.endswith('>'):
                    return url_match[1:-1]

        return None
