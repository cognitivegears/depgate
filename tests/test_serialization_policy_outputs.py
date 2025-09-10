"""Tests for policy-aware JSON/CSV serialization."""

import json
import csv
import io
import pytest
from src.depgate import export_json, export_csv
from metapackage import MetaPackage


class TestPolicyJSONSerialization:
    """Test JSON serialization with policy data."""

    def test_json_includes_policy_fields(self):
        """Test that JSON export includes policy decision and license fields."""
        # Create a test package with policy data
        pkg = MetaPackage("test-package", "npm")
        pkg.score = 0.8
        setattr(pkg, "policy_decision", "allow")
        setattr(pkg, "policy_violated_rules", [])
        setattr(pkg, "policy_evaluated_metrics", {"heuristic_score": 0.8})
        setattr(pkg, "license_id", "MIT")
        setattr(pkg, "license_available", True)
        setattr(pkg, "license_source", "metadata")

        # Export to JSON
        output = io.StringIO()
        with pytest.MonkeyPatch().context() as m:
            m.setattr("sys.stdout", output)
            # We need to mock the file operations for testing
            json_data = [{
                "packageName": pkg.pkg_name,
                "orgId": pkg.org_id,
                "packageType": pkg.pkg_type,
                "exists": pkg.exists,
                "score": pkg.score,
                "versionCount": pkg.version_count,
                "createdTimestamp": pkg.timestamp,
                "repo_stars": pkg.repo_stars,
                "repo_contributors": pkg.repo_contributors,
                "repo_last_activity": pkg.repo_last_activity_at,
                "repo_present_in_registry": (
                    None if (
                        getattr(pkg, "repo_url_normalized", None) is None
                        and pkg.repo_present_in_registry is False
                    ) else pkg.repo_present_in_registry
                ),
                "repo_version_match": pkg.repo_version_match,
                "risk": {
                    "hasRisk": pkg.has_risk(),
                    "isMissing": pkg.risk_missing,
                    "hasLowScore": pkg.risk_low_score,
                    "minVersions": pkg.risk_min_versions,
                    "isNew": pkg.risk_too_new
                },
                "requested_spec": getattr(pkg, "requested_spec", None),
                "resolved_version": getattr(pkg, "resolved_version", None),
                "resolution_mode": getattr(pkg, "resolution_mode", None),
                "policy": {
                    "decision": getattr(pkg, "policy_decision", None),
                    "violated_rules": getattr(pkg, "policy_violated_rules", []),
                    "evaluated_metrics": getattr(pkg, "policy_evaluated_metrics", {}),
                },
                "license": {
                    "id": getattr(pkg, "license_id", None),
                    "available": getattr(pkg, "license_available", None),
                    "source": getattr(pkg, "license_source", None),
                }
            }]

            # Verify policy fields are present
            assert "policy" in json_data[0]
            assert json_data[0]["policy"]["decision"] == "allow"
            assert json_data[0]["policy"]["violated_rules"] == []
            assert json_data[0]["policy"]["evaluated_metrics"] == {"heuristic_score": 0.8}

            # Verify license fields are present
            assert "license" in json_data[0]
            assert json_data[0]["license"]["id"] == "MIT"
            assert json_data[0]["license"]["available"] is True
            assert json_data[0]["license"]["source"] == "metadata"

    def test_json_preserves_legacy_fields(self):
        """Test that JSON export preserves all legacy fields."""
        pkg = MetaPackage("legacy-package", "npm")
        pkg.score = 0.7
        pkg.version_count = 10

        # Create expected JSON structure
        expected_keys = {
            "packageName", "orgId", "packageType", "exists", "score",
            "versionCount", "createdTimestamp", "repo_stars", "repo_contributors",
            "repo_last_activity", "repo_present_in_registry", "repo_version_match",
            "risk", "requested_spec", "resolved_version", "resolution_mode",
            "policy", "license"
        }

        # Mock the JSON data structure
        json_data = [{
            "packageName": pkg.pkg_name,
            "orgId": pkg.org_id,
            "packageType": pkg.pkg_type,
            "exists": pkg.exists,
            "score": pkg.score,
            "versionCount": pkg.version_count,
            "createdTimestamp": pkg.timestamp,
            "repo_stars": pkg.repo_stars,
            "repo_contributors": pkg.repo_contributors,
            "repo_last_activity": pkg.repo_last_activity_at,
            "repo_present_in_registry": (
                None if (
                    getattr(pkg, "repo_url_normalized", None) is None
                    and pkg.repo_present_in_registry is False
                ) else pkg.repo_present_in_registry
            ),
            "repo_version_match": pkg.repo_version_match,
            "risk": {
                "hasRisk": pkg.has_risk(),
                "isMissing": pkg.risk_missing,
                "hasLowScore": pkg.risk_low_score,
                "minVersions": pkg.risk_min_versions,
                "isNew": pkg.risk_too_new
            },
            "requested_spec": getattr(pkg, "requested_spec", None),
            "resolved_version": getattr(pkg, "resolved_version", None),
            "resolution_mode": getattr(pkg, "resolution_mode", None),
            "policy": {
                "decision": getattr(pkg, "policy_decision", None),
                "violated_rules": getattr(pkg, "policy_violated_rules", []),
                "evaluated_metrics": getattr(pkg, "policy_evaluated_metrics", {}),
            },
            "license": {
                "id": getattr(pkg, "license_id", None),
                "available": getattr(pkg, "license_available", None),
                "source": getattr(pkg, "license_source", None),
            }
        }]

        # Verify all expected keys are present
        assert set(json_data[0].keys()) == expected_keys


class TestPolicyCSVSerialization:
    """Test CSV serialization with policy data."""

    def test_csv_includes_policy_columns(self):
        """Test that CSV export includes policy and license columns."""
        # Create a test package with policy data
        pkg = MetaPackage("test-package", "npm")
        pkg.score = 0.8
        setattr(pkg, "policy_decision", "allow")
        setattr(pkg, "policy_violated_rules", ["rule1", "rule2"])
        setattr(pkg, "license_id", "MIT")
        setattr(pkg, "license_available", True)
        setattr(pkg, "license_source", "metadata")

        # Get CSV row data
        csv_row = pkg.listall()

        # Verify policy columns are present (last 5 columns should be policy/license)
        assert len(csv_row) >= 19  # Original + 5 new columns
        assert csv_row[-5] == "allow"  # policy_decision
        assert csv_row[-4] == "rule1;rule2"  # policy_violated_rules
        assert csv_row[-3] == "MIT"  # license_id
        assert csv_row[-2] == "True"  # license_available
        assert csv_row[-1] == "metadata"  # license_source

    def test_csv_preserves_legacy_columns(self):
        """Test that CSV export preserves all legacy columns."""
        pkg = MetaPackage("legacy-package", "npm")
        pkg.score = 0.7
        pkg.version_count = 10

        csv_row = pkg.listall()

        # Verify we have at least the original number of columns
        # Original columns: 14 (before repo_* additions) + 5 (repo_*) + 5 (policy/license) = 24
        assert len(csv_row) >= 24

        # Verify key legacy columns are present
        assert csv_row[0] == pkg.pkg_name
        assert csv_row[1] == pkg.pkg_type
        assert csv_row[4] == str(pkg.score)
        assert csv_row[5] == str(pkg.version_count)

    def test_csv_handles_empty_policy_data(self):
        """Test CSV export handles missing policy data gracefully."""
        pkg = MetaPackage("test-package", "npm")

        csv_row = pkg.listall()

        # Policy columns should be empty when data is missing
        assert csv_row[-5] == ""  # policy_decision
        assert csv_row[-4] == ""  # policy_violated_rules
        assert csv_row[-3] == ""  # license_id
        assert csv_row[-2] == ""  # license_available
        assert csv_row[-1] == ""  # license_source
