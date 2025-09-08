"""Unit tests for GitHub API client."""
from __future__ import annotations

import pytest
from unittest.mock import patch, Mock

from repository.github import GitHubClient


class TestGitHubClient:
    """Test cases for GitHubClient class."""

    def test_initialization_default(self):
        """Test client initialization with defaults."""
        client = GitHubClient()
        assert client.base_url == "https://api.github.com"
        assert client.token is None

    def test_initialization_custom(self):
        """Test client initialization with custom values."""
        client = GitHubClient(base_url="https://custom.api.com", token="test-token")
        assert client.base_url == "https://custom.api.com"
        assert client.token == "test-token"

    def test_initialization_with_env_token(self):
        """Test client initialization reads token from environment."""
        with patch.dict('os.environ', {'GITHUB_TOKEN': 'env-token'}):
            client = GitHubClient()
            assert client.token == "env-token"

    def test_get_headers_without_token(self):
        """Test headers generation without token."""
        client = GitHubClient()
        headers = client._get_headers()
        assert 'Accept' in headers
        assert 'Authorization' not in headers

    def test_get_headers_with_token(self):
        """Test headers generation with token."""
        client = GitHubClient(token="test-token")
        headers = client._get_headers()
        assert headers['Authorization'] == "token test-token"

    @patch('repository.github.get_json')
    def test_get_repo_success(self, mock_get_json):
        """Test successful repository metadata retrieval."""
        mock_get_json.return_value = (200, {}, {
            'stargazers_count': 42,
            'pushed_at': '2023-01-01T00:00:00Z',
            'default_branch': 'main'
        })

        client = GitHubClient()
        result = client.get_repo('owner', 'repo')

        assert result is not None
        assert result['stargazers_count'] == 42
        assert result['pushed_at'] == '2023-01-01T00:00:00Z'
        assert result['default_branch'] == 'main'

        mock_get_json.assert_called_once_with(
            'https://api.github.com/repos/owner/repo',
            headers={'Accept': 'application/vnd.github.v3+json'}
        )

    @patch('repository.github.get_json')
    def test_get_repo_failure(self, mock_get_json):
        """Test repository retrieval failure."""
        mock_get_json.return_value = (404, {}, None)

        client = GitHubClient()
        result = client.get_repo('owner', 'repo')

        assert result is None

    @patch('repository.github.get_json')
    def test_get_tags_paginated(self, mock_get_json):
        """Test paginated tags retrieval."""
        # Mock responses for pagination
        mock_get_json.side_effect = [
            (200, {'link': '<https://api.github.com/repos/owner/repo/tags?page=2>; rel="next"'}, [{'name': 'v1.0.0'}]),
            (200, {}, [{'name': 'v0.9.0'}])
        ]

        client = GitHubClient()
        result = client.get_tags('owner', 'repo')

        assert len(result) == 2
        assert result[0]['name'] == 'v1.0.0'
        assert result[1]['name'] == 'v0.9.0'

    @patch('repository.github.get_json')
    def test_get_releases_paginated(self, mock_get_json):
        """Test paginated releases retrieval."""
        mock_get_json.side_effect = [
            (200, {'link': '<https://api.github.com/repos/owner/repo/releases?page=2>; rel="next"'}, [{'tag_name': 'v1.0.0'}]),
            (200, {}, [{'tag_name': 'v0.9.0'}])
        ]

        client = GitHubClient()
        result = client.get_releases('owner', 'repo')

        assert len(result) == 2
        assert result[0]['tag_name'] == 'v1.0.0'
        assert result[1]['tag_name'] == 'v0.9.0'

    @patch('repository.github.get_json')
    def test_get_contributors_count_with_link_header(self, mock_get_json):
        """Test contributor count using Link header for total."""
        mock_get_json.return_value = (200, {
            'link': '<https://api.github.com/repos/owner/repo/contributors?page=1>; rel="first", <https://api.github.com/repos/owner/repo/contributors?page=5>; rel="last"'
        }, [{'login': 'user1'}, {'login': 'user2'}])

        client = GitHubClient()
        result = client.get_contributors_count('owner', 'repo')

        assert result == 5  # From last page

    @patch('repository.github.get_json')
    def test_get_contributors_count_fallback(self, mock_get_json):
        """Test contributor count fallback when Link header unavailable."""
        mock_get_json.return_value = (200, {}, [{'login': 'user1'}, {'login': 'user2'}])

        client = GitHubClient()
        result = client.get_contributors_count('owner', 'repo')

        assert result == 2  # Count of returned items

    @patch('repository.github.get_json')
    def test_get_contributors_count_failure(self, mock_get_json):
        """Test contributor count on API failure."""
        mock_get_json.return_value = (404, {}, None)

        client = GitHubClient()
        result = client.get_contributors_count('owner', 'repo')

        assert result is None

    def test_parse_link_header_next_page(self):
        """Test parsing next page URL from Link header."""
        client = GitHubClient()
        link_header = '<https://api.github.com/repos/owner/repo/tags?page=2>; rel="next"'
        next_url = client._get_next_page_url(link_header)

        assert next_url == 'https://api.github.com/repos/owner/repo/tags?page=2'

    def test_parse_link_header_no_next(self):
        """Test parsing Link header without next page."""
        client = GitHubClient()
        link_header = '<https://api.github.com/repos/owner/repo/tags?page=1>; rel="first"'
        next_url = client._get_next_page_url(link_header)

        assert next_url is None

    def test_parse_link_header_total_from_last(self):
        """Test parsing total count from Link header with last page."""
        client = GitHubClient()
        link_header = '<https://api.github.com/repos/owner/repo/contributors?page=5>; rel="last"'
        total = client._parse_link_header_total(link_header)

        assert total == 5

    def test_parse_link_header_total_no_last(self):
        """Test parsing total count when no last page in Link header."""
        client = GitHubClient()
        link_header = '<https://api.github.com/repos/owner/repo/contributors?page=1>; rel="first"'
        total = client._parse_link_header_total(link_header)

        assert total is None
