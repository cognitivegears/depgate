"""Tests for PEP 503 package name normalization in PyPI client."""
import json
from unittest.mock import patch, Mock, call

from metapackage import MetaPackage
from registry.pypi.client import (
    _sanitize_identifier,
    recv_pkg_info as pypi_recv_pkg_info,
    PYPSTATS_RECENT_URL,
    HEADERS_JSON,
)


class TestSanitizeIdentifier:
    """Test _sanitize_identifier strips specifiers but preserves raw name."""

    def test_plain_name(self):
        assert _sanitize_identifier("requests") == "requests"

    def test_version_specifier(self):
        assert _sanitize_identifier("requests>=2.0") == "requests"

    def test_extras(self):
        assert _sanitize_identifier("requests[security]") == "requests"

    def test_marker(self):
        assert _sanitize_identifier("requests;python_version>='3'") == "requests"

    def test_mixed_case_preserved(self):
        """Sanitize should NOT normalize case—that's canonicalize_name's job."""
        assert _sanitize_identifier("Flask_RESTful>=0.3") == "Flask_RESTful"


class TestPEP503Normalization:
    """Verify recv_pkg_info applies PEP 503 normalization to URLs."""

    def _make_pypi_response(self):
        resp = Mock()
        resp.status_code = 200
        resp.text = json.dumps({
            "info": {"version": "1.0.0"},
            "releases": {
                "1.0.0": [{"upload_time_iso_8601": "2023-01-01T00:00:00.000Z"}]
            },
        })
        return resp

    def _make_stats_response(self, last_week=5000):
        resp = Mock()
        resp.status_code = 200
        resp.text = json.dumps({"data": {"last_week": last_week}})
        return resp

    @patch("registry.pypi.client.pypi_pkg.safe_get")
    def test_underscore_package_normalized_in_pypi_url(self, mock_get):
        """Flask_RESTful should query pypi as flask-restful."""
        pkg = MetaPackage("Flask_RESTful", "pypi")

        mock_get.side_effect = [self._make_pypi_response(), self._make_stats_response()]

        pypi_recv_pkg_info([pkg])

        pypi_call = mock_get.call_args_list[0]
        url = pypi_call[0][0]
        assert "flask-restful/json" in url
        assert "Flask_RESTful" not in url

    @patch("registry.pypi.client.pypi_pkg.safe_get")
    def test_underscore_package_normalized_in_stats_url(self, mock_get):
        """pypistats URL should also use the normalized name."""
        pkg = MetaPackage("Flask_RESTful", "pypi")

        mock_get.side_effect = [self._make_pypi_response(), self._make_stats_response()]

        pypi_recv_pkg_info([pkg])

        stats_call = mock_get.call_args_list[1]
        stats_url = stats_call[0][0]
        assert stats_url == PYPSTATS_RECENT_URL.format(package="flask-restful")

    @patch("registry.pypi.client.pypi_pkg.safe_get")
    def test_dot_separated_package_normalized(self, mock_get):
        """zope.interface → zope-interface in URLs."""
        pkg = MetaPackage("zope.interface", "pypi")

        mock_get.side_effect = [self._make_pypi_response(), self._make_stats_response()]

        pypi_recv_pkg_info([pkg])

        pypi_url = mock_get.call_args_list[0][0][0]
        stats_url = mock_get.call_args_list[1][0][0]
        assert "zope-interface/json" in pypi_url
        assert "zope-interface" in stats_url

    @patch("registry.pypi.client.pypi_pkg.safe_get")
    def test_mixed_case_package_normalized(self, mock_get):
        """PyYAML → pyyaml in URLs."""
        pkg = MetaPackage("PyYAML", "pypi")

        mock_get.side_effect = [self._make_pypi_response(), self._make_stats_response()]

        pypi_recv_pkg_info([pkg])

        pypi_url = mock_get.call_args_list[0][0][0]
        stats_url = mock_get.call_args_list[1][0][0]
        assert "pyyaml/json" in pypi_url
        assert "pyyaml" in stats_url

    @patch("registry.pypi.client.pypi_pkg.safe_get")
    def test_already_normalized_name_unchanged(self, mock_get):
        """Already-normalized names should pass through cleanly."""
        pkg = MetaPackage("requests", "pypi")

        mock_get.side_effect = [self._make_pypi_response(), self._make_stats_response()]

        pypi_recv_pkg_info([pkg])

        pypi_url = mock_get.call_args_list[0][0][0]
        stats_url = mock_get.call_args_list[1][0][0]
        assert "requests/json" in pypi_url
        assert "requests" in stats_url

    @patch("registry.pypi.client.pypi_pkg.safe_get")
    def test_version_specifier_stripped_then_normalized(self, mock_get):
        """Flask_RESTful>=0.3 should sanitize then normalize."""
        pkg = MetaPackage("Flask_RESTful>=0.3", "pypi")

        mock_get.side_effect = [self._make_pypi_response(), self._make_stats_response()]

        pypi_recv_pkg_info([pkg])

        pypi_url = mock_get.call_args_list[0][0][0]
        assert "flask-restful/json" in pypi_url
