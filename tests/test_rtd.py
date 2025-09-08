"""Unit tests for Read the Docs repository resolution."""
from __future__ import annotations

import pytest
from unittest.mock import patch, Mock

from repository.rtd import infer_rtd_slug, resolve_repo_from_rtd


class TestInferRTDSlug:
    """Test cases for RTD slug inference."""

    def test_readthedocs_org_url(self):
        """Test slug extraction from readthedocs.org/projects/slug format."""
        url = "https://readthedocs.org/projects/myproject/"
        result = infer_rtd_slug(url)
        assert result == "myproject"

    def test_readthedocs_io_url(self):
        """Test slug extraction from *.readthedocs.io format."""
        url = "https://myproject.readthedocs.io/"
        result = infer_rtd_slug(url)
        assert result == "myproject"

    def test_readthedocs_io_with_path(self):
        """Test slug extraction with additional path."""
        url = "https://myproject.readthedocs.io/en/latest/"
        result = infer_rtd_slug(url)
        assert result == "myproject"

    def test_non_rtd_url(self):
        """Test non-RTD URL returns None."""
        url = "https://github.com/owner/repo"
        result = infer_rtd_slug(url)
        assert result is None

    def test_empty_url(self):
        """Test empty URL returns None."""
        result = infer_rtd_slug("")
        assert result is None

    def test_none_url(self):
        """Test None URL returns None."""
        result = infer_rtd_slug(None)
        assert result is None


class TestResolveRepoFromRTD:
    """Test cases for repository resolution from RTD."""

    @patch('repository.rtd.get_json')
    def test_successful_resolution_detail_endpoint(self, mock_get_json):
        """Test successful resolution via detail endpoint."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {
            'repository': {'url': 'https://github.com/owner/repo'}
        }
        mock_get_json.return_value = (200, {}, mock_response.json.return_value)

        result = resolve_repo_from_rtd("https://myproject.readthedocs.io/")
        assert result == "https://github.com/owner/repo"
        mock_get_json.assert_called_once()

    @patch('repository.rtd.get_json')
    def test_fallback_to_slug_search(self, mock_get_json):
        """Test fallback to slug search when detail endpoint fails."""
        # First call (detail endpoint) returns 404
        mock_get_json.side_effect = [
            (404, {}, None),  # Detail endpoint fails
            (200, {}, {'results': [{'repository': {'url': 'https://github.com/owner/repo'}}]})  # Slug search succeeds
        ]

        result = resolve_repo_from_rtd("https://myproject.readthedocs.io/")
        assert result == "https://github.com/owner/repo"
        assert mock_get_json.call_count == 2

    @patch('repository.rtd.get_json')
    def test_fallback_to_name_search(self, mock_get_json):
        """Test fallback to name search when both detail and slug search fail."""
        mock_get_json.side_effect = [
            (404, {}, None),  # Detail endpoint fails
            (200, {}, {'results': []}),  # Slug search returns no results
            (200, {}, {'results': [{'repository': {'url': 'https://github.com/owner/repo'}}]})  # Name search succeeds
        ]

        result = resolve_repo_from_rtd("https://myproject.readthedocs.io/")
        assert result == "https://github.com/owner/repo"
        assert mock_get_json.call_count == 3

    @patch('repository.rtd.get_json')
    def test_no_repository_url_in_response(self, mock_get_json):
        """Test handling when response doesn't contain repository URL."""
        mock_get_json.return_value = (200, {}, {'repository': {}})

        result = resolve_repo_from_rtd("https://myproject.readthedocs.io/")
        assert result is None

    @patch('repository.rtd.get_json')
    def test_all_endpoints_fail(self, mock_get_json):
        """Test when all API endpoints fail or return no results."""
        mock_get_json.return_value = (404, {}, None)

        result = resolve_repo_from_rtd("https://myproject.readthedocs.io/")
        assert result is None

    @patch('repository.rtd.get_json')
    def test_non_rtd_url(self, mock_get_json):
        """Test non-RTD URL returns None without API calls."""
        result = resolve_repo_from_rtd("https://github.com/owner/repo")
        assert result is None
        mock_get_json.assert_not_called()

    @patch('repository.rtd.get_json')
    def test_empty_results_list(self, mock_get_json):
        """Test handling of empty results in fallback searches."""
        mock_get_json.side_effect = [
            (404, {}, None),  # Detail endpoint fails
            (200, {}, {'results': []}),  # Slug search returns empty
            (200, {}, {'results': []})   # Name search returns empty
        ]

        result = resolve_repo_from_rtd("https://myproject.readthedocs.io/")
        assert result is None
