"""Tests for provider adapters with new metrics."""
import pytest
from unittest.mock import Mock, patch

from repository.provider_adapters import GitHubProviderAdapter, GitLabProviderAdapter


class TestGitHubProviderAdapterNewMetrics:
    """Test GitHubProviderAdapter with new methods."""

    def test_get_repo_info_includes_new_fields(self):
        """Test that get_repo_info includes forks and open_issues."""
        mock_client = Mock()
        mock_client.get_repo.return_value = {
            'stargazers_count': 100,
            'pushed_at': '2023-01-01T00:00:00Z',
            'default_branch': 'main',
            'forks_count': 25,
            'open_issues_count': 10
        }

        adapter = GitHubProviderAdapter(client=mock_client)
        result = adapter.get_repo_info('owner', 'repo')

        assert result is not None
        assert result['stars'] == 100
        assert result['last_activity_at'] == '2023-01-01T00:00:00Z'
        assert result['forks_count'] == 25
        assert result['open_issues_count'] == 10

    def test_get_open_prs_count(self):
        """Test get_open_prs_count delegates to client."""
        mock_client = Mock()
        mock_client.get_open_prs_count.return_value = 5

        adapter = GitHubProviderAdapter(client=mock_client)
        result = adapter.get_open_prs_count('owner', 'repo')

        assert result == 5
        mock_client.get_open_prs_count.assert_called_once_with('owner', 'repo')

    def test_get_last_commit(self):
        """Test get_last_commit delegates to client."""
        mock_client = Mock()
        mock_client.get_last_commit.return_value = '2023-12-01T10:00:00Z'

        adapter = GitHubProviderAdapter(client=mock_client)
        result = adapter.get_last_commit('owner', 'repo')

        assert result == '2023-12-01T10:00:00Z'
        mock_client.get_last_commit.assert_called_once_with('owner', 'repo')

    def test_get_last_merged_pr(self):
        """Test get_last_merged_pr delegates to client."""
        mock_client = Mock()
        mock_client.get_last_merged_pr.return_value = '2023-11-15T10:00:00Z'

        adapter = GitHubProviderAdapter(client=mock_client)
        result = adapter.get_last_merged_pr('owner', 'repo')

        assert result == '2023-11-15T10:00:00Z'
        mock_client.get_last_merged_pr.assert_called_once_with('owner', 'repo')

    def test_get_last_closed_issue(self):
        """Test get_last_closed_issue delegates to client."""
        mock_client = Mock()
        mock_client.get_last_closed_issue.return_value = '2023-11-20T10:00:00Z'

        adapter = GitHubProviderAdapter(client=mock_client)
        result = adapter.get_last_closed_issue('owner', 'repo')

        assert result == '2023-11-20T10:00:00Z'
        mock_client.get_last_closed_issue.assert_called_once_with('owner', 'repo')


class TestGitLabProviderAdapterNewMetrics:
    """Test GitLabProviderAdapter with new methods."""

    def test_get_repo_info_includes_new_fields(self):
        """Test that get_repo_info includes forks and open_issues."""
        mock_client = Mock()
        mock_client.get_project.return_value = {
            'star_count': 100,
            'last_activity_at': '2023-01-01T00:00:00Z',
            'default_branch': 'main',
            'forks_count': 25,
            'open_issues_count': 10
        }

        adapter = GitLabProviderAdapter(client=mock_client)
        result = adapter.get_repo_info('owner', 'repo')

        assert result is not None
        assert result['stars'] == 100
        assert result['last_activity_at'] == '2023-01-01T00:00:00Z'
        assert result['forks_count'] == 25
        assert result['open_issues_count'] == 10

    def test_get_open_prs_count(self):
        """Test get_open_prs_count delegates to client."""
        mock_client = Mock()
        mock_client.get_open_prs_count.return_value = 3

        adapter = GitLabProviderAdapter(client=mock_client)
        result = adapter.get_open_prs_count('owner', 'repo')

        assert result == 3
        mock_client.get_open_prs_count.assert_called_once_with('owner', 'repo')

    def test_get_last_commit(self):
        """Test get_last_commit delegates to client."""
        mock_client = Mock()
        mock_client.get_last_commit.return_value = '2023-12-01T10:00:00Z'

        adapter = GitLabProviderAdapter(client=mock_client)
        result = adapter.get_last_commit('owner', 'repo')

        assert result == '2023-12-01T10:00:00Z'
        mock_client.get_last_commit.assert_called_once_with('owner', 'repo')

    def test_get_last_merged_pr(self):
        """Test get_last_merged_pr delegates to client."""
        mock_client = Mock()
        mock_client.get_last_merged_pr.return_value = '2023-11-15T10:00:00Z'

        adapter = GitLabProviderAdapter(client=mock_client)
        result = adapter.get_last_merged_pr('owner', 'repo')

        assert result == '2023-11-15T10:00:00Z'
        mock_client.get_last_merged_pr.assert_called_once_with('owner', 'repo')

    def test_get_last_closed_issue(self):
        """Test get_last_closed_issue delegates to client."""
        mock_client = Mock()
        mock_client.get_last_closed_issue.return_value = '2023-11-20T10:00:00Z'

        adapter = GitLabProviderAdapter(client=mock_client)
        result = adapter.get_last_closed_issue('owner', 'repo')

        assert result == '2023-11-20T10:00:00Z'
        mock_client.get_last_closed_issue.assert_called_once_with('owner', 'repo')

