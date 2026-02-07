"""Tests for weekly downloads extraction from npm and PyPI."""
import json
from unittest.mock import patch, Mock

from metapackage import MetaPackage
from registry.npm.client import recv_pkg_info as npm_recv_pkg_info
from registry.pypi.client import recv_pkg_info as pypi_recv_pkg_info


class TestNPMWeeklyDownloads:
    """Test weekly downloads extraction from npm/npms.io API."""

    @patch('registry.npm.client.npm_pkg.safe_post')
    def test_weekly_downloads_extracted(self, mock_post):
        """Test that weekly downloads are extracted from npms.io response."""
        pkg = MetaPackage("test-package", "npm")

        # Mock npms.io response with downloadsCount
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({
            "test-package": {
                "score": {"final": 0.8},
                "collected": {"metadata": {"date": "2023-01-01T00:00:00.000Z"}},
                "evaluation": {
                    "popularity": {
                        "downloadsCount": 50000
                    }
                }
            }
        })

        mock_post.return_value = mock_response

        npm_recv_pkg_info([pkg], should_fetch_details=False)

        assert pkg.weekly_downloads == 50000

    @patch('registry.npm.client.npm_pkg.safe_post')
    def test_weekly_downloads_missing(self, mock_post):
        """Test that missing downloadsCount doesn't break processing."""
        pkg = MetaPackage("test-package", "npm")

        # Mock npms.io response without downloadsCount
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({
            "test-package": {
                "score": {"final": 0.8},
                "collected": {"metadata": {"date": "2023-01-01T00:00:00.000Z"}}
            }
        })

        mock_post.return_value = mock_response

        npm_recv_pkg_info([pkg], should_fetch_details=False)

        assert pkg.weekly_downloads is None

    @patch('registry.npm.client.npm_pkg.safe_post')
    def test_weekly_downloads_zero(self, mock_post):
        """Test that zero downloads are handled correctly."""
        pkg = MetaPackage("test-package", "npm")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = json.dumps({
            "test-package": {
                "score": {"final": 0.8},
                "collected": {"metadata": {"date": "2023-01-01T00:00:00.000Z"}},
                "evaluation": {
                    "popularity": {
                        "downloadsCount": 0
                    }
                }
            }
        })

        mock_post.return_value = mock_response

        npm_recv_pkg_info([pkg], should_fetch_details=False)

        assert pkg.weekly_downloads == 0


class TestPyPIWeeklyDownloads:
    """Test weekly downloads extraction from PyPI/pypistats.org API."""

    @patch('registry.pypi.client.pypi_pkg.safe_get')
    def test_weekly_downloads_extracted(self, mock_get):
        """Test that weekly downloads are extracted from pypistats.org."""
        pkg = MetaPackage("test-package", "pypi")

        # Mock PyPI JSON response
        pypi_response = Mock()
        pypi_response.status_code = 200
        pypi_response.text = json.dumps({
            "info": {"version": "1.0.0"},
            "releases": {"1.0.0": [{"upload_time_iso_8601": "2023-01-01T00:00:00.000Z"}]}
        })

        # Mock pypistats.org response
        stats_response = Mock()
        stats_response.status_code = 200
        stats_response.text = json.dumps({
            "data": {
                "last_week": 25000
            }
        })

        mock_get.side_effect = [pypi_response, stats_response]

        pypi_recv_pkg_info([pkg])

        assert pkg.weekly_downloads == 25000

    @patch('registry.pypi.client.pypi_pkg.safe_get')
    def test_weekly_downloads_stats_api_failure(self, mock_get):
        """Test that pypistats.org API failure doesn't break processing."""
        pkg = MetaPackage("test-package", "pypi")

        # Mock PyPI JSON response
        pypi_response = Mock()
        pypi_response.status_code = 200
        pypi_response.text = json.dumps({
            "info": {"version": "1.0.0"},
            "releases": {"1.0.0": [{"upload_time_iso_8601": "2023-01-01T00:00:00.000Z"}]}
        })

        # Mock pypistats.org failure
        stats_response = Mock()
        stats_response.status_code = 404

        mock_get.side_effect = [pypi_response, stats_response]

        pypi_recv_pkg_info([pkg])

        # Package should still be processed, weekly_downloads should be None
        assert pkg.exists is True
        assert pkg.weekly_downloads is None

    @patch('registry.pypi.client.pypi_pkg.safe_get')
    def test_weekly_downloads_stats_missing_field(self, mock_get):
        """Test that missing last_week field doesn't break processing."""
        pkg = MetaPackage("test-package", "pypi")

        # Mock PyPI JSON response
        pypi_response = Mock()
        pypi_response.status_code = 200
        pypi_response.text = json.dumps({
            "info": {"version": "1.0.0"},
            "releases": {"1.0.0": [{"upload_time_iso_8601": "2023-01-01T00:00:00.000Z"}]}
        })

        # Mock pypistats.org response without last_week
        stats_response = Mock()
        stats_response.status_code = 200
        stats_response.text = json.dumps({
            "data": {}
        })

        mock_get.side_effect = [pypi_response, stats_response]

        pypi_recv_pkg_info([pkg])

        assert pkg.exists is True
        assert pkg.weekly_downloads is None

    @patch('registry.pypi.client.pypi_pkg.safe_get')
    def test_weekly_downloads_zero(self, mock_get):
        """Test that zero weekly downloads are handled correctly."""
        pkg = MetaPackage("test-package", "pypi")

        # Mock PyPI JSON response
        pypi_response = Mock()
        pypi_response.status_code = 200
        pypi_response.text = json.dumps({
            "info": {"version": "1.0.0"},
            "releases": {"1.0.0": [{"upload_time_iso_8601": "2023-01-01T00:00:00.000Z"}]}
        })

        # Mock pypistats.org response with zero downloads
        stats_response = Mock()
        stats_response.status_code = 200
        stats_response.text = json.dumps({
            "data": {
                "last_week": 0
            }
        })

        mock_get.side_effect = [pypi_response, stats_response]

        pypi_recv_pkg_info([pkg])

        assert pkg.weekly_downloads == 0

