"""Tests for registry client structured logging instrumentation."""

import logging
import pytest
from unittest.mock import patch, Mock

from common.logging_utils import correlation_context, request_context
from metapackage import MetaPackage
from registry.npm.client import get_package_details as npm_get_package_details
from registry.pypi.client import recv_pkg_info as pypi_recv_pkg_info
from registry.maven.client import recv_pkg_info as maven_recv_pkg_info
from registry.npm.client import recv_pkg_info as npm_recv_pkg_info


class TestNPMClientLogging:
    """Test logging instrumentation for NPM client."""

    def test_get_package_details_logging_success(self, caplog):
        """Test logging for successful get_package_details."""
        with caplog.at_level(logging.DEBUG):
            with correlation_context("test-corr-id"), request_context("test-req-id"):
                pkg = MetaPackage("test-package")

                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.text = '{"versions": {"1.0.0": {}}}'

                with patch('registry.npm.client.npm_pkg.safe_get', return_value=mock_response):
                    npm_get_package_details(pkg, "https://registry.npmjs.org")

                records = [r for r in caplog.records if r.name == 'registry.npm.client']

                # Should have pre-call DEBUG log
                pre_call_logs = [r for r in records if r.message == "HTTP request"]
                assert len(pre_call_logs) == 1
                assert pre_call_logs[0].event == "http_request"
                assert pre_call_logs[0].package_manager == "npm"

                # Should have success log
                success_logs = [r for r in records if r.message == "HTTP response ok"]
                assert len(success_logs) == 1
                assert success_logs[0].outcome == "success"

    def test_safe_url_redaction(self, caplog):
        """Test that URLs with sensitive parameters are redacted."""
        with caplog.at_level(logging.DEBUG):
            pkg = MetaPackage("test-package")

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = '{"versions": {"1.0.0": {}}}'

            with patch('registry.npm.client.npm_pkg.safe_get', return_value=mock_response):
                npm_get_package_details(pkg, "https://registry.npmjs.org?token=secret123")

            records = [r for r in caplog.records if r.name == 'registry.npm.client']
            for record in records:
                if hasattr(record, 'target'):
                    assert "secret123" not in record.target
                    # URL encoding turns [REDACTED] into %5BREDACTED%5D
                    assert "%5BREDACTED%5D" in record.target


class TestPyPIClientLogging:
    """Test logging instrumentation for PyPI client."""

    def test_recv_pkg_info_logging_success(self, caplog):
        """Test logging for successful PyPI package info retrieval."""
        with caplog.at_level(logging.DEBUG):
            pkg = MetaPackage("test-pypi-pkg")

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = '{"info": {"version": "1.0.0"}, "releases": {"1.0.0": []}}'

            with patch('registry.pypi.client.pypi_pkg.safe_get', return_value=mock_response):
                pypi_recv_pkg_info([pkg])

            records = [r for r in caplog.records if r.name == 'registry.pypi.client']

            # Should have pre-call DEBUG log
            pre_call_logs = [r for r in records if r.message == "HTTP request"]
            assert len(pre_call_logs) == 1
            assert pre_call_logs[0].event == "http_request"
            assert pre_call_logs[0].package_manager == "pypi"

            # Should have success log
            success_logs = [r for r in records if r.message == "HTTP response ok"]
            assert len(success_logs) == 1
            assert success_logs[0].outcome == "success"


class TestMavenClientLogging:
    """Test logging instrumentation for Maven client."""

    def test_recv_pkg_info_logging_success(self, caplog):
        """Test logging for successful Maven package info retrieval."""
        with caplog.at_level(logging.DEBUG):
            pkg = MetaPackage("test-maven", pkgorg="com.example")

            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = '{"response": {"numFound": 1, "docs": [{"timestamp": 1234567890}]}}'

            with patch('common.http_client.safe_get', return_value=mock_response):
                maven_recv_pkg_info([pkg])

            records = [r for r in caplog.records if r.name == 'registry.maven.client']

            # Should have pre-call DEBUG log
            pre_call_logs = [r for r in records if r.message == "HTTP request"]
            assert len(pre_call_logs) == 1
            assert pre_call_logs[0].event == "http_request"
            assert pre_call_logs[0].package_manager == "maven"

            # Should have success log
            success_logs = [r for r in records if r.message == "HTTP response ok"]
            assert len(success_logs) == 1
            assert success_logs[0].outcome == "success"


class TestCorrelationAndRequestIDs:
    """Test that correlation and request IDs are properly included in logs."""

    def test_ids_included_in_logs(self, caplog):
        """Test that correlation and request IDs appear in log records."""
        with caplog.at_level(logging.DEBUG):
            with correlation_context("test-correlation"), request_context("test-request"):
                pkg = MetaPackage("test-package")

                mock_response = Mock()
                mock_response.status_code = 200
                mock_response.text = '{"versions": {"1.0.0": {}}}'

                with patch('registry.npm.client.npm_pkg.safe_get', return_value=mock_response):
                    npm_get_package_details(pkg, "https://registry.npmjs.org")

                records = [r for r in caplog.records if r.name == 'registry.npm.client']
                for record in records:
                    if hasattr(record, '__dict__'):
                        assert record.correlation_id == "test-correlation"
                        assert record.request_id == "test-request"


class TestNPMClientScopedEncoding:
    """Ensure scoped package names are percent-encoded in URL path."""

    def test_scoped_package_url_is_percent_encoded(self):
        pkg = MetaPackage("@biomejs/biome")

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = '{"versions": {"1.0.0": {}}}'

        with patch('registry.npm.client.npm_pkg.safe_get', return_value=mock_response) as mock_get:
            npm_get_package_details(pkg, "https://registry.npmjs.org")

            called_url = mock_get.call_args[0][0]
            assert "%40biomejs%2Fbiome" in called_url
            assert "@biomejs/biome" not in called_url
