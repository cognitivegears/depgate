"""Integration-style tests for logging across discovery/enrichment flows."""

import logging
import pytest
from unittest.mock import patch, Mock

from common.logging_utils import correlation_context, request_context, configure_logging
from metapackage import MetaPackage
from registry.npm.discovery import _parse_repository_field, _extract_fallback_urls
from registry.pypi.discovery import _extract_repo_candidates
from registry.npm.enrich import _enrich_with_repo as npm_enrich_with_repo
from registry.pypi.enrich import _enrich_with_repo as pypi_enrich_with_repo


class TestLoggingIntegrationE2E:
    """Integration tests for logging across complete discovery/enrichment flows."""

    def test_npm_discovery_enrichment_flow_logging_info_level(self, caplog):
        """Test complete NPM flow with INFO level logging."""
        # Configure logging at INFO level
        configure_logging()
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        with caplog.at_level(logging.INFO):
            with correlation_context("int-e2e-corr"), request_context("int-e2e-req"):
                # Simulate NPM discovery
                version_info = {
                    "repository": {"type": "git", "url": "git+https://github.com/o/r.git"},
                    "homepage": "https://github.com/o/r#readme",
                    "bugs": {"url": "https://github.com/o/r/issues"}
                }

                _parse_repository_field(version_info)
                _extract_fallback_urls(version_info)

                # Simulate NPM enrichment
                mp = MetaPackage("test-npm-pkg")
                packument = {
                    "dist-tags": {"latest": "1.0.0"},
                    "versions": {
                        "1.0.0": {
                            "repository": "https://github.com/o/r",
                            "homepage": "https://github.com/o/r#readme"
                        }
                    }
                }

                # Mock dependencies to avoid network calls
                with patch('registry.npm.enrich.npm_pkg.normalize_repo_url') as mock_normalize:
                    mock_normalize.return_value = Mock(normalized_url="https://github.com/o/r", host="github")
                    with patch('registry.npm.enrich.ProviderRegistry.get') as mock_provider:
                        mock_provider.return_value = Mock()
                        with patch('registry.npm.enrich.ProviderValidationService.validate_and_populate'):
                            npm_enrich_with_repo(mp, packument)

        # Verify INFO level logs
        info_records = [r for r in caplog.records if r.levelname == "INFO"]

        # Should have milestone logs for enrichment
        milestone_logs = [r for r in info_records if r.event in {"start", "complete"}]
        assert len(milestone_logs) >= 1

        # Should NOT have DEBUG function entry/exit logs
        debug_records = [r for r in caplog.records if r.levelname == "DEBUG"]
        entry_logs = [r for r in debug_records if r.event == "function_entry"]
        assert len(entry_logs) == 0

        # Verify correlation/request IDs are present
        for record in caplog.records:
            if hasattr(record, 'correlation_id'):
                assert record.correlation_id == "int-e2e-corr"
            if hasattr(record, 'request_id'):
                assert record.request_id == "int-e2e-req"

    def test_pypi_discovery_enrichment_flow_logging_info_level(self, caplog):
        """Test complete PyPI flow with INFO level logging."""
        # Configure logging at INFO level
        configure_logging()
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        with caplog.at_level(logging.INFO):
            with correlation_context("int-e2e-corr"), request_context("int-e2e-req"):
                # Simulate PyPI discovery
                info = {
                    "project_urls": {"Repository": "https://gitlab.com/o/r"},
                    "version": "2.0.0"
                }

                _extract_repo_candidates(info)

                # Simulate PyPI enrichment
                mp = MetaPackage("test-pypi-pkg")

                # Mock dependencies to avoid network calls
                with patch('registry.pypi.enrich.pypi_pkg.normalize_repo_url') as mock_normalize:
                    mock_normalize.return_value = Mock(normalized_url="https://gitlab.com/o/r", host="gitlab")
                    with patch('registry.pypi.enrich.ProviderRegistry.get') as mock_provider:
                        mock_provider.return_value = Mock()
                        with patch('registry.pypi.enrich.ProviderValidationService.validate_and_populate'):
                            pypi_enrich_with_repo(mp, "test-pypi-pkg", info, "2.0.0")

        # Verify INFO level logs
        info_records = [r for r in caplog.records if r.levelname == "INFO"]

        # Should have milestone logs for enrichment
        milestone_logs = [r for r in info_records if r.event in {"start", "complete"}]
        assert len(milestone_logs) >= 1

        # Should NOT have DEBUG function entry/exit logs
        debug_records = [r for r in caplog.records if r.levelname == "DEBUG"]
        entry_logs = [r for r in debug_records if r.event == "function_entry"]
        assert len(entry_logs) == 0

    def test_npm_discovery_enrichment_flow_logging_debug_level(self, caplog):
        """Test complete NPM flow with DEBUG level logging."""
        # Configure logging at DEBUG level
        configure_logging()
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        with caplog.at_level(logging.DEBUG):
            with correlation_context("int-e2e-corr"), request_context("int-e2e-req"):
                # Simulate NPM discovery
                version_info = {
                    "repository": {"type": "git", "url": "git+https://github.com/o/r.git"},
                    "homepage": "https://github.com/o/r#readme",
                    "bugs": {"url": "https://github.com/o/r/issues"}
                }

                _parse_repository_field(version_info)
                _extract_fallback_urls(version_info)

                # Simulate NPM enrichment
                mp = MetaPackage("test-npm-pkg")
                packument = {
                    "dist-tags": {"latest": "1.0.0"},
                    "versions": {
                        "1.0.0": {
                            "repository": "https://github.com/o/r",
                            "homepage": "https://github.com/o/r#readme"
                        }
                    }
                }

                # Mock dependencies to avoid network calls
                with patch('registry.npm.enrich.npm_pkg.normalize_repo_url') as mock_normalize:
                    mock_normalize.return_value = Mock(normalized_url="https://github.com/o/r", host="github")
                    with patch('registry.npm.enrich.ProviderRegistry.get') as mock_provider:
                        mock_provider.return_value = Mock()
                        with patch('registry.npm.enrich.ProviderValidationService.validate_and_populate'):
                            npm_enrich_with_repo(mp, packument)

        # Verify DEBUG level logs
        debug_records = [r for r in caplog.records if r.levelname == "DEBUG"]

        # Should have function entry logs
        entry_logs = [r for r in debug_records if r.event == "function_entry"]
        assert len(entry_logs) >= 2  # At least discovery and enrichment entries

        # Should have function exit logs
        exit_logs = [r for r in debug_records if r.event == "function_exit"]
        assert len(exit_logs) >= 2

        # Should have decision logs
        decision_logs = [r for r in debug_records if r.event == "decision"]
        assert len(decision_logs) >= 1

        # Verify reasonable log volume (should not be excessive)
        total_records = len(caplog.records)
        assert total_records < 300  # Reasonable upper bound for this flow

        # Verify correlation/request IDs are present
        for record in caplog.records:
            if hasattr(record, 'correlation_id'):
                assert record.correlation_id == "int-e2e-corr"
            if hasattr(record, 'request_id'):
                assert record.request_id == "int-e2e-req"

    def test_pypi_discovery_enrichment_flow_logging_debug_level(self, caplog):
        """Test complete PyPI flow with DEBUG level logging."""
        # Configure logging at DEBUG level
        configure_logging()
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        with caplog.at_level(logging.DEBUG):
            with correlation_context("int-e2e-corr"), request_context("int-e2e-req"):
                # Simulate PyPI discovery
                info = {
                    "project_urls": {"Repository": "https://gitlab.com/o/r"},
                    "version": "2.0.0"
                }

                _extract_repo_candidates(info)

                # Simulate PyPI enrichment
                mp = MetaPackage("test-pypi-pkg")

                # Mock dependencies to avoid network calls
                with patch('registry.pypi.enrich.pypi_pkg.normalize_repo_url') as mock_normalize:
                    mock_normalize.return_value = Mock(normalized_url="https://gitlab.com/o/r", host="gitlab")
                    with patch('registry.pypi.enrich.ProviderRegistry.get') as mock_provider:
                        mock_provider.return_value = Mock()
                        with patch('registry.pypi.enrich.ProviderValidationService.validate_and_populate'):
                            pypi_enrich_with_repo(mp, "test-pypi-pkg", info, "2.0.0")

        # Verify DEBUG level logs
        debug_records = [r for r in caplog.records if r.levelname == "DEBUG"]

        # Should have function entry logs
        entry_logs = [r for r in debug_records if r.event == "function_entry"]
        assert len(entry_logs) >= 2  # At least discovery and enrichment entries

        # Should have function exit logs
        exit_logs = [r for r in debug_records if r.event == "function_exit"]
        assert len(exit_logs) >= 2

        # Should have decision logs
        decision_logs = [r for r in debug_records if r.event == "decision"]
        assert len(decision_logs) >= 1

        # Verify reasonable log volume
        total_records = len(caplog.records)
        assert total_records < 300

    def test_no_sensitive_data_in_logs(self, caplog):
        """Test that sensitive data is not leaked in logs."""
        configure_logging()
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        with caplog.at_level(logging.DEBUG):
            # Test with URLs containing tokens
            version_info = {
                "repository": {"type": "git", "url": "git+https://github.com/o/r.git?token=secret123"},
                "homepage": "https://github.com/o/r#readme?api_key=apikey456",
                "bugs": {"url": "https://github.com/o/r/issues?access_token=token789"}
            }

            _parse_repository_field(version_info)
            _extract_fallback_urls(version_info)

        # Verify no sensitive data appears in any log messages
        for record in caplog.records:
            assert "secret123" not in record.message
            assert "apikey456" not in record.message
            assert "token789" not in record.message
            assert "token=" not in record.message
            assert "api_key=" not in record.message
            assert "access_token=" not in record.message

    def test_correlation_request_ids_attached(self, caplog):
        """Test that correlation and request IDs are properly attached to log records."""
        configure_logging()
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)

        with caplog.at_level(logging.DEBUG):
            with correlation_context("test-corr-123"), request_context("test-req-456"):
                version_info = {
                    "repository": {"type": "git", "url": "git+https://github.com/o/r.git"},
                }

                _parse_repository_field(version_info)

        # Verify IDs are attached to records
        sampled_records = caplog.records[:5]  # Sample first few records
        for record in sampled_records:
            if hasattr(record, '__dict__'):
                assert record.correlation_id == "test-corr-123"
                assert record.request_id == "test-req-456"
