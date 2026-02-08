"""Tests for MetaPackage new properties."""
from datetime import datetime, timezone

from metapackage import MetaPackage


class TestMetaPackageNewProperties:
    """Test new properties in MetaPackage."""

    def test_weekly_downloads_property(self):
        """Test weekly_downloads property getter and setter."""
        mp = MetaPackage("test-package", "npm")

        assert mp.weekly_downloads is None

        mp.weekly_downloads = 50000
        assert mp.weekly_downloads == 50000

        mp.weekly_downloads = None
        assert mp.weekly_downloads is None

    def test_repo_forks_property(self):
        """Test repo_forks property getter and setter."""
        mp = MetaPackage("test-package", "npm")

        assert mp.repo_forks is None

        mp.repo_forks = 25
        assert mp.repo_forks == 25

        mp.repo_forks = None
        assert mp.repo_forks is None

    def test_repo_open_issues_property(self):
        """Test repo_open_issues property getter and setter."""
        mp = MetaPackage("test-package", "npm")

        assert mp.repo_open_issues is None

        mp.repo_open_issues = 10
        assert mp.repo_open_issues == 10

        mp.repo_open_issues = None
        assert mp.repo_open_issues is None

    def test_repo_open_prs_property(self):
        """Test repo_open_prs property getter and setter."""
        mp = MetaPackage("test-package", "npm")

        assert mp.repo_open_prs is None

        mp.repo_open_prs = 3
        assert mp.repo_open_prs == 3

        mp.repo_open_prs = None
        assert mp.repo_open_prs is None

    def test_repo_last_commit_at_property(self):
        """Test repo_last_commit_at property getter and setter."""
        mp = MetaPackage("test-package", "npm")

        assert mp.repo_last_commit_at is None

        timestamp = "2023-12-01T10:00:00Z"
        mp.repo_last_commit_at = timestamp
        assert mp.repo_last_commit_at == timestamp

        mp.repo_last_commit_at = None
        assert mp.repo_last_commit_at is None

    def test_repo_last_merged_pr_at_property(self):
        """Test repo_last_merged_pr_at property getter and setter."""
        mp = MetaPackage("test-package", "npm")

        assert mp.repo_last_merged_pr_at is None

        timestamp = "2023-11-15T10:00:00Z"
        mp.repo_last_merged_pr_at = timestamp
        assert mp.repo_last_merged_pr_at == timestamp

        mp.repo_last_merged_pr_at = None
        assert mp.repo_last_merged_pr_at is None

    def test_repo_last_closed_issue_at_property(self):
        """Test repo_last_closed_issue_at property getter and setter."""
        mp = MetaPackage("test-package", "npm")

        assert mp.repo_last_closed_issue_at is None

        timestamp = "2023-11-20T10:00:00Z"
        mp.repo_last_closed_issue_at = timestamp
        assert mp.repo_last_closed_issue_at == timestamp

        mp.repo_last_closed_issue_at = None
        assert mp.repo_last_closed_issue_at is None

    def test_all_new_properties_initialized(self):
        """Test that all new properties are initialized to None."""
        mp = MetaPackage("test-package", "npm")

        assert mp.weekly_downloads is None
        assert mp.repo_forks is None
        assert mp.repo_open_issues is None
        assert mp.repo_open_prs is None
        assert mp.repo_last_commit_at is None
        assert mp.repo_last_merged_pr_at is None
        assert mp.repo_last_closed_issue_at is None

    def test_supply_chain_trust_properties(self):
        """Trust/provenance fields should be settable for heuristics/policy use."""
        mp = MetaPackage("test-package", "npm")

        assert mp.provenance_present is None
        assert mp.registry_signature_present is None
        assert mp.trust_score is None
        assert mp.previous_trust_score is None
        assert mp.trust_score_delta is None

        mp.provenance_present = True
        mp.registry_signature_present = True
        mp.previous_provenance_present = False
        mp.previous_registry_signature_present = True
        mp.provenance_regressed = False
        mp.registry_signature_regressed = False
        mp.trust_score = 1.0
        mp.previous_trust_score = 0.5
        mp.trust_score_delta = 0.5
        mp.trust_score_decreased = False
        mp.previous_release_version = "1.2.2"
        mp.release_age_days = 30

        assert mp.provenance_present is True
        assert mp.registry_signature_present is True
        assert mp.previous_provenance_present is False
        assert mp.previous_registry_signature_present is True
        assert mp.trust_score == 1.0
        assert mp.previous_trust_score == 0.5
        assert mp.trust_score_delta == 0.5
        assert mp.trust_score_decreased is False
        assert mp.previous_release_version == "1.2.2"
        assert mp.release_age_days == 30
