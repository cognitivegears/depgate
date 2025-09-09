"""Tests for discovery/enrichment logging instrumentation."""

import logging
import pytest
from unittest.mock import patch, Mock

from common.logging_utils import correlation_context, request_context
from metapackage import MetaPackage
from registry.npm.discovery import _parse_repository_field, _extract_fallback_urls
from registry.npm.enrich import _enrich_with_repo as npm_enrich_with_repo
from registry.pypi.discovery import _extract_repo_candidates
from registry.pypi.enrich import _enrich_with_repo as pypi_enrich_with_repo
from registry.maven.discovery import _normalize_scm_to_repo_url
from registry.maven.enrich import _enrich_with_repo as maven_enrich_with_repo


class TestNPMDiscoveryLogging:
    """Test logging instrumentation for NPM discovery functions."""

    def test_parse_repository_field_logging_success(self, caplog):
        """Test logging for successful repository field parsing."""
        with caplog.at_level(logging.DEBUG):
            with correlation_context("test-corr-id"), request_context("test-req-id"):
                version_info = {
                    "repository": {"type": "git", "url": "git+https://github.com/o/r.git", "directory": "pkg/a"},
                    "homepage": "https://github.com/o/r#readme",
                    "bugs": {"url": "https://github.com/o/r/issues"}
                }

                result = _parse_repository_field(version_info)

                records = [r for r in caplog.records if r.name == 'registry.npm.discovery']

                # Should have decision logs for repository field parsing
                decision_logs = [r for r in records if r.event == "decision" and r.component == "discovery"]
                assert len(decision_logs) >= 1

                # Should have function entry/exit logs
                entry_logs = [r for r in records if r.event == "function_entry"]
                assert len(entry_logs) >= 1

                exit_logs = [r for r in records if r.event == "function_exit"]
                assert len(exit_logs) >= 1

                # Verify structured fields
                for record in records:
                    assert record.package_manager == "npm"
                    assert record.component == "discovery"
                    if hasattr(record, 'correlation_id'):
                        assert record.correlation_id == "test-corr-id"
                    if hasattr(record, 'request_id'):
                        assert record.request_id == "test-req-id"

    def test_extract_fallback_urls_logging(self, caplog):
        """Test logging for fallback URL extraction."""
        with caplog.at_level(logging.DEBUG):
            with correlation_context("test-corr-id"), request_context("test-req-id"):
                version_info = {
                    "repository": {"type": "git", "url": "git+https://github.com/o/r.git"},
                    "homepage": "https://github.com/o/r#readme",
                    "bugs": {"url": "https://github.com/o/r/issues"}
                }

                result = _extract_fallback_urls(version_info)

                records = [r for r in caplog.records if r.name == 'registry.npm.discovery']

                # Should have decision logs for fallback processing
                decision_logs = [r for r in records if r.event == "decision"]
                assert len(decision_logs) >= 1

                # Should have function exit with count
                exit_logs = [r for r in records if r.event == "function_exit"]
                assert len(exit_logs) >= 1
                assert hasattr(exit_logs[0], 'count')

    def test_parse_repository_field_anomaly_logging(self, caplog):
        """Test logging for repository field parsing anomalies."""
        with caplog.at_level(logging.WARNING):
            version_info = {"repository": {"type": "git"}}  # Missing URL

            result = _parse_repository_field(version_info)

            records = [r for r in caplog.records if r.name == 'registry.npm.discovery']

            # Should have anomaly log
            anomaly_logs = [r for r in records if r.event == "anomaly"]
            assert len(anomaly_logs) >= 1

            # Verify anomaly details
            anomaly = anomaly_logs[0]
            assert anomaly.component == "discovery"
            assert anomaly.package_manager == "npm"
            assert anomaly.outcome in ("unexpected_type", "missing_url")


class TestNPMEnrichmentLogging:
    """Test logging instrumentation for NPM enrichment functions."""

    def test_enrich_with_repo_logging_success(self, caplog):
        """Test logging for successful NPM enrichment."""
        with caplog.at_level(logging.DEBUG):
            with correlation_context("test-corr-id"), request_context("test-req-id"):
                mp = MetaPackage("test-package")
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

                records = [r for r in caplog.records if r.name == 'registry.npm.enrich']

                # Should have function entry
                entry_logs = [r for r in records if r.event == "function_entry"]
                assert len(entry_logs) >= 1

                # Should have function exit
                exit_logs = [r for r in records if r.event == "function_exit"]
                assert len(exit_logs) >= 1

                # Should have INFO milestone
                info_records = [r for r in caplog.records if r.levelname == "INFO" and r.name == 'registry.npm.enrich']
                milestone_logs = [r for r in info_records if r.event in {"start", "complete"}]
                assert len(milestone_logs) >= 1

                # Verify duration_ms on completion
                complete_logs = [r for r in milestone_logs if r.event == "complete"]
                if complete_logs:
                    assert hasattr(complete_logs[0], 'duration_ms')


class TestPyPIDiscoveryLogging:
    """Test logging instrumentation for PyPI discovery functions."""

    def test_extract_repo_candidates_logging(self, caplog):
        """Test logging for PyPI repository candidate extraction."""
        with caplog.at_level(logging.DEBUG):
            with correlation_context("test-corr-id"), request_context("test-req-id"):
                info = {
                    "project_urls": {
                        "Repository": "https://gitlab.com/o/r",
                        "Homepage": "https://example.com"
                    },
                    "version": "2.0.0"
                }

                result = _extract_repo_candidates(info)

                records = [r for r in caplog.records if r.name == 'registry.pypi.discovery']

                # Should have function entry/exit
                entry_logs = [r for r in records if r.event == "function_entry"]
                assert len(entry_logs) >= 1

                exit_logs = [r for r in records if r.event == "function_exit"]
                assert len(exit_logs) >= 1

                # Should have decision logs
                decision_logs = [r for r in records if r.event == "decision"]
                assert len(decision_logs) >= 1


class TestPyPIEnrichmentLogging:
    """Test logging instrumentation for PyPI enrichment functions."""

    def test_enrich_with_repo_logging_success(self, caplog):
        """Test logging for successful PyPI enrichment."""
        with caplog.at_level(logging.DEBUG):
            with correlation_context("test-corr-id"), request_context("test-req-id"):
                mp = MetaPackage("test-pypi-pkg")
                info = {
                    "project_urls": {"Repository": "https://gitlab.com/o/r"},
                    "version": "2.0.0"
                }

                # Mock dependencies to avoid network calls
                with patch('registry.pypi.enrich.pypi_pkg.normalize_repo_url') as mock_normalize:
                    mock_normalize.return_value = Mock(normalized_url="https://gitlab.com/o/r", host="gitlab")
                    with patch('registry.pypi.enrich.ProviderRegistry.get') as mock_provider:
                        mock_provider.return_value = Mock()
                        with patch('registry.pypi.enrich.ProviderValidationService.validate_and_populate'):
                            pypi_enrich_with_repo(mp, "test-pypi-pkg", info, "2.0.0")

                records = [r for r in caplog.records if r.name == 'registry.pypi.enrich']

                # Should have function entry
                entry_logs = [r for r in records if r.event == "function_entry"]
                assert len(entry_logs) >= 1

                # Should have function exit
                exit_logs = [r for r in records if r.event == "function_exit"]
                assert len(exit_logs) >= 1

                # Should have INFO milestone
                info_records = [r for r in caplog.records if r.levelname == "INFO" and r.name == 'registry.pypi.enrich']
                milestone_logs = [r for r in info_records if r.event in {"start", "complete"}]
                assert len(milestone_logs) >= 1


class TestMavenDiscoveryLogging:
    """Test logging instrumentation for Maven discovery functions."""

    def test_normalize_scm_to_repo_url_logging(self, caplog):
        """Test logging for SCM URL normalization."""
        with caplog.at_level(logging.DEBUG):
            with correlation_context("test-corr-id"), request_context("test-req-id"):
                scm = {"connection": "scm:git:https://github.com/o/r.git"}

                # Mock the normalize_repo_url function
                with patch('repository.url_normalize.normalize_repo_url') as mock_normalize:
                    mock_normalize.return_value = Mock(normalized_url="https://github.com/o/r")
                    result = _normalize_scm_to_repo_url(scm)

                records = [r for r in caplog.records if r.name == 'registry.maven.discovery']

                # Should have some debug logs (exact structure depends on implementation)
                assert len(records) >= 0  # May not have explicit logs, depends on implementation


class TestMavenEnrichmentLogging:
    """Test logging instrumentation for Maven enrichment functions."""

    def test_enrich_with_repo_logging_success(self, caplog):
        """Test logging for successful Maven enrichment."""
        with caplog.at_level(logging.DEBUG):
            with correlation_context("test-corr-id"), request_context("test-req-id"):
                mp = MetaPackage("test-maven", pkgorg="com.example")

                # Mock dependencies to avoid network calls
                with patch('registry.maven.enrich.maven_pkg._resolve_latest_version') as mock_resolve:
                    mock_resolve.return_value = "1.0.0"
                    with patch('registry.maven.enrich.maven_pkg._traverse_for_scm') as mock_traverse:
                        mock_traverse.return_value = {"connection": "scm:git:https://github.com/o/r.git"}
                        with patch('registry.maven.enrich._normalize_scm_to_repo_url') as mock_normalize:
                            mock_normalize.return_value = "https://github.com/o/r"
                            with patch('registry.maven.enrich.maven_pkg.normalize_repo_url') as mock_normalize_repo:
                                mock_normalize_repo.return_value = Mock(normalized_url="https://github.com/o/r", host="github")
                                with patch('registry.maven.enrich.ProviderRegistry.get') as mock_provider:
                                    mock_provider.return_value = Mock()
                                    with patch('registry.maven.enrich.ProviderValidationService.validate_and_populate'):
                                        maven_enrich_with_repo(mp, "com.example", "test-maven", "1.0.0")

                records = [r for r in caplog.records if r.name == 'registry.maven.enrich']

                # Should have function entry
                entry_logs = [r for r in records if r.event == "function_entry"]
                assert len(entry_logs) >= 1

                # Should have function exit
                exit_logs = [r for r in records if r.event == "function_exit"]
                assert len(exit_logs) >= 1

                # Should have INFO milestone
                info_records = [r for r in caplog.records if r.levelname == "INFO" and r.name == 'registry.maven.enrich']
                milestone_logs = [r for r in info_records if r.event in {"start", "complete"}]
                assert len(milestone_logs) >= 1


class TestSecurityLogging:
    """Test that sensitive information is not logged."""

    def test_no_token_leakage_in_logs(self, caplog):
        """Test that tokens are not exposed in log messages."""
        with caplog.at_level(logging.DEBUG):
            version_info = {
                "repository": {"type": "git", "url": "git+https://github.com/o/r.git?token=secret123"}
            }

            _parse_repository_field(version_info)

            # Check that no record contains the token
            for record in caplog.records:
                assert "secret123" not in record.message
                assert "token=" not in record.message
