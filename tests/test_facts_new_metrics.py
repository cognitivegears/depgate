"""Tests for facts builder with new metrics."""
import pytest
from datetime import datetime, timezone, timedelta

from metapackage import MetaPackage
from analysis.facts import FactBuilder


class TestFactsBuilderNewMetrics:
    """Test FactBuilder with new metrics."""

    def test_facts_includes_new_metrics(self):
        """Test that facts include all new metrics."""
        mp = MetaPackage("test-package", "npm")
        mp.weekly_downloads = 50000
        mp.download_count = 1000000
        mp.repo_forks = 25
        mp.repo_open_issues = 10
        mp.repo_open_prs = 3
        mp.repo_last_commit_at = "2023-12-01T10:00:00Z"
        mp.repo_last_merged_pr_at = "2023-11-15T10:00:00Z"
        mp.repo_last_closed_issue_at = "2023-11-20T10:00:00Z"
        mp.release_age_days = 10
        mp.trust_score = 0.75
        mp.previous_trust_score = 0.5
        mp.trust_score_delta = 0.25
        mp.trust_score_decreased = False
        mp.provenance_present = True
        mp.previous_provenance_present = False
        mp.provenance_regressed = False
        mp.registry_signature_present = True
        mp.previous_registry_signature_present = True
        mp.registry_signature_regressed = False
        mp.previous_release_version = "1.0.0"

        builder = FactBuilder()
        facts = builder.build_facts(mp)

        assert facts["weekly_downloads"] == 50000
        assert facts["forks_count"] == 25
        assert facts["open_issues_count"] == 10
        assert facts["open_prs_count"] == 3
        assert facts["last_commit_at"] == "2023-12-01T10:00:00Z"
        assert facts["last_merged_pr_at"] == "2023-11-15T10:00:00Z"
        assert facts["last_closed_issue_at"] == "2023-11-20T10:00:00Z"
        assert facts["release_age_days"] == 10
        assert facts["supply_chain_trust_score"] == 0.75
        assert facts["supply_chain_previous_trust_score"] == 0.5
        assert facts["supply_chain_trust_score_delta"] == 0.25
        assert facts["supply_chain_trust_score_decreased"] is False
        assert facts["provenance_present"] is True
        assert facts["previous_provenance_present"] is False
        assert facts["provenance_regressed"] is False
        assert facts["registry_signature_present"] is True
        assert facts["previous_registry_signature_present"] is True
        assert facts["registry_signature_regressed"] is False
        assert facts["previous_release_version"] == "1.0.0"

    def test_facts_new_metrics_none(self):
        """Test that facts handle None values for new metrics."""
        mp = MetaPackage("test-package", "npm")
        # Leave all new metrics as None

        builder = FactBuilder()
        facts = builder.build_facts(mp)

        assert facts["weekly_downloads"] is None
        assert facts["forks_count"] is None
        assert facts["open_issues_count"] is None
        assert facts["open_prs_count"] is None
        assert facts["last_commit_at"] is None
        assert facts["last_merged_pr_at"] is None
        assert facts["last_closed_issue_at"] is None
        assert facts["release_age_days"] is None
        assert facts["supply_chain_trust_score"] is None
        assert facts["provenance_present"] is None
        assert facts["registry_signature_present"] is None

    def test_facts_all_metrics_present(self):
        """Test facts with all metrics including new ones."""
        mp = MetaPackage("test-package", "npm")
        mp.score = 0.8
        mp.repo_stars = 1000
        mp.repo_contributors = 50
        mp.weekly_downloads = 75000
        mp.repo_forks = 100
        mp.repo_open_issues = 5
        mp.repo_open_prs = 2
        mp.repo_last_commit_at = "2023-12-01T10:00:00Z"
        mp.repo_last_merged_pr_at = "2023-11-15T10:00:00Z"
        mp.repo_last_closed_issue_at = "2023-11-20T10:00:00Z"
        mp.repo_version_match = {"matched": True}
        mp.trust_score = 1.0
        mp.provenance_present = True
        mp.registry_signature_present = True

        builder = FactBuilder()
        facts = builder.build_facts(mp)

        # Check all metrics are present
        assert facts["heuristic_score"] == 0.8
        assert facts["stars_count"] == 1000
        assert facts["contributors_count"] == 50
        assert facts["weekly_downloads"] == 75000
        assert facts["forks_count"] == 100
        assert facts["open_issues_count"] == 5
        assert facts["open_prs_count"] == 2
        assert facts["last_commit_at"] == "2023-12-01T10:00:00Z"
        assert facts["last_merged_pr_at"] == "2023-11-15T10:00:00Z"
        assert facts["last_closed_issue_at"] == "2023-11-20T10:00:00Z"
        assert facts["supply_chain_trust_score"] == 1.0
        assert facts["provenance_present"] is True
        assert facts["registry_signature_present"] is True
