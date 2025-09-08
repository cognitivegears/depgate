"""Unit tests for GitLab API client."""
from __future__ import annotations

import pytest
from unittest.mock import patch, Mock

from repository.gitlab import GitLabClient


class TestGitLabClient:
    """Test cases for GitLabClient class."""

    def test_initialization_default(self):
        """Test client initialization with defaults."""
        client = GitLabClient()
        assert client.base_url == "https://gitlab.com/api/v4"
        assert client.token is None

    def test_initialization_custom(self):
        """Test client initialization with custom values."""
        client = GitLabClient(base_url="https://custom.gitlab.com/api/v4", token="test-token")
        assert client.base_url == "https://custom.gitlab.com/api/v4"
        assert client.token == "test-token"

    def test_initialization_with_env_token(self):
        """Test client initialization reads token from environment."""
        with patch.dict('os.environ', {'GITLAB_TOKEN': 'env-token'}):
            client = GitLabClient()
            assert client.token == "env-token"

    def test_get_headers_without_token(self):
        """Test headers generation without token."""
        client = GitLabClient()
        headers = client._get_headers()
        assert headers == {}

    def test_get_headers_with_token(self):
        """Test headers generation with token."""
        client = GitLabClient(token="test-token")
        headers = client._get_headers()
        assert headers['Private-Token'] == "test-token"

    @patch('repository.gitlab.get_json')
    def test_get_project_success(self, mock_get_json):
        """Test successful project metadata retrieval."""
        mock_get_json.return_value = (200, {}, {
            'star_count': 42,
            'last_activity_at': '2023-01-01T00:00:00Z',
            'default_branch': 'main'
        })

        client = GitLabClient()
        result = client.get_project('owner', 'repo')

        assert result is not None
        assert result['star_count'] == 42
        assert result['last_activity_at'] == '2023-01-01T00:00:00Z'
        assert result['default_branch'] == 'main'

        mock_get_json.assert_called_once_with(
            'https://gitlab.com/api/v4/projects/owner%2Frepo',
            headers={}
        )

    @patch('repository.gitlab.get_json')
    def test_get_project_failure(self, mock_get_json):
        """Test project retrieval failure."""
        mock_get_json.return_value = (404, {}, None)

        client = GitLabClient()
        result = client.get_project('owner', 'repo')

        assert result is None

    @patch('repository.gitlab.get_json')
    def test_get_tags_paginated(self, mock_get_json):
        """Test paginated tags retrieval."""
        # Mock responses for pagination
        mock_get_json.side_effect = [
            (200, {'x-page': '1', 'x-total-pages': '2'}, [{'name': 'v1.0.0'}]),
            (200, {'x-page': '2', 'x-total-pages': '2'}, [{'name': 'v0.9.0'}])
        ]

        client = GitLabClient()
        result = client.get_tags('owner', 'repo')

        assert len(result) == 2
        assert result[0]['name'] == 'v1.0.0'
        assert result[1]['name'] == 'v0.9.0'

    @patch('repository.gitlab.get_json')
    def test_get_releases_paginated(self, mock_get_json):
        """Test paginated releases retrieval."""
        mock_get_json.side_effect = [
            (200, {'x-page': '1', 'x-total-pages': '2'}, [{'tag_name': 'v1.0.0'}]),
            (200, {'x-page': '2', 'x-total-pages': '2'}, [{'tag_name': 'v0.9.0'}])
        ]

        client = GitLabClient()
        result = client.get_releases('owner', 'repo')

        assert len(result) == 2
        assert result[0]['tag_name'] == 'v1.0.0'
        assert result[1]['tag_name'] == 'v0.9.0'

    @patch('repository.gitlab.get_json')
    def test_get_contributors_count_success(self, mock_get_json):
        """Test successful contributor count retrieval."""
        mock_get_json.return_value = (200, {}, [
            {'name': 'user1'},
            {'name': 'user2'},
            {'name': 'user3'}
        ])

        client = GitLabClient()
        result = client.get_contributors_count('owner', 'repo')

        assert result == 3

    @patch('repository.gitlab.get_json')
    def test_get_contributors_count_failure(self, mock_get_json):
        """Test contributor count on API failure."""
        mock_get_json.return_value = (404, {}, None)

        client = GitLabClient()
        result = client.get_contributors_count('owner', 'repo')

        assert result is None

    def test_get_current_page(self):
        """Test extracting current page from headers."""
        client = GitLabClient()
        headers = {'x-page': '3'}
        result = client._get_current_page(headers)
        assert result == 3

    def test_get_current_page_missing(self):
        """Test handling missing page header."""
        client = GitLabClient()
        headers = {}
        result = client._get_current_page(headers)
        assert result is None

    def test_get_total_pages(self):
        """Test extracting total pages from headers."""
        client = GitLabClient()
        headers = {'x-total-pages': '10'}
        result = client._get_total_pages(headers)
        assert result == 10

    def test_get_total_pages_missing(self):
        """Test handling missing total pages header."""
        client = GitLabClient()
        headers = {}
        result = client._get_total_pages(headers)
        assert result is None

    @patch('repository.gitlab.get_json')
    def test_pagination_stops_at_last_page(self, mock_get_json):
        """Test pagination stops when reaching last page."""
        mock_get_json.side_effect = [
            (200, {'x-page': '1', 'x-total-pages': '1'}, [{'name': 'v1.0.0'}])
        ]

        client = GitLabClient()
        result = client.get_tags('owner', 'repo')

        assert len(result) == 1
        assert result[0]['name'] == 'v1.0.0'
        # Should only call once since we're already at the last page
        assert mock_get_json.call_count == 1

    @patch('repository.gitlab.get_json')
    def test_pagination_handles_invalid_page_numbers(self, mock_get_json):
        """Test pagination handles invalid page numbers gracefully."""
        mock_get_json.return_value = (200, {'x-page': 'invalid', 'x-total-pages': 'invalid'}, [])

        client = GitLabClient()
        result = client.get_tags('owner', 'repo')

        assert result == []
        # Should stop pagination due to invalid page numbers
        assert mock_get_json.call_count == 1
