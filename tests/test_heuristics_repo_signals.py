"""Unit tests for repository signals scoring in heuristics."""
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock
from metapackage import MetaPackage
from analysis.heuristics import compute_repo_signals_score


class TestRepositorySignalsScoring(unittest.TestCase):
    """Test cases for repository signals scoring function."""

    def setUp(self):
        """Set up test fixtures."""
        self.mp = MetaPackage("test-package")

    def test_strong_github_case(self):
        """Test strong GitHub case with all positive signals."""
        # Set up a strong positive case
        self.mp.repo_resolved = True
        self.mp.repo_exists = True
        self.mp.repo_present_in_registry = True
        self.mp.repo_version_match = {'matched': True}
        self.mp.repo_last_activity_at = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        self.mp.repo_stars = 5000  # log10(5000) + 1 = 4.7 -> floor to 4
        self.mp.repo_contributors = 200  # log10(200) + 1 = 3.3 -> floor to 3

        score = compute_repo_signals_score(self.mp)

        # Expected: +15 (version match) +8 (resolved+exists) +2 (present) +6 (recent) +4 (stars) +3 (contributors) = +38
        # Clamped to +30 max
        self.assertEqual(score, 30)

    def test_resolved_no_version_match(self):
        """Test resolved repo but no version match."""
        self.mp.repo_resolved = True
        self.mp.repo_exists = True
        self.mp.repo_present_in_registry = True
        self.mp.repo_version_match = {'matched': False}  # No match found
        self.mp.repo_last_activity_at = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        self.mp.repo_stars = 100  # log10(100) + 1 = 3
        self.mp.repo_contributors = 50  # log10(50) + 1 = 2.7 -> floor to 2

        score = compute_repo_signals_score(self.mp)

        # Expected: -8 (no version match) +8 (resolved+exists) +2 (present) +6 (recent) +3 (stars) +2 (contributors) = +13
        self.assertEqual(score, 13)

    def test_present_in_registry_unresolved(self):
        """Test present in registry but unresolved."""
        self.mp.repo_resolved = False
        self.mp.repo_present_in_registry = True
        # No other fields set

        score = compute_repo_signals_score(self.mp)

        # Expected: +2 (present in registry only)
        self.assertEqual(score, 2)

    def test_repo_exists_false(self):
        """Test case where repo exists is False."""
        self.mp.repo_resolved = True
        self.mp.repo_exists = False
        self.mp.repo_present_in_registry = True

        score = compute_repo_signals_score(self.mp)

        # Expected: -5 (resolved but exists=False) +2 (present) = -3
        self.assertEqual(score, -3)

    def test_very_stale_activity(self):
        """Test very stale activity with low engagement."""
        self.mp.repo_resolved = True
        self.mp.repo_exists = True
        self.mp.repo_present_in_registry = True
        self.mp.repo_last_activity_at = (datetime.now(timezone.utc) - timedelta(days=800)).isoformat()  # > 2 years
        self.mp.repo_stars = 10  # log10(10) + 1 = 2
        self.mp.repo_contributors = 5  # log10(5) + 1 = 1.7 -> floor to 1

        score = compute_repo_signals_score(self.mp)

        # Expected: +8 (resolved+exists) +2 (present) -2 (stale) +2 (stars) +1 (contributors) = +11
        self.assertEqual(score, 11)

    def test_missing_fields_everywhere(self):
        """Test case with all fields missing/None."""
        # All fields remain as None/False (default values)
        score = compute_repo_signals_score(self.mp)

        # Expected: 0 (no signals available)
        self.assertEqual(score, 0)

    def test_version_match_unknown(self):
        """Test version match unknown (None)."""
        self.mp.repo_resolved = True
        self.mp.repo_exists = True
        self.mp.repo_present_in_registry = True
        self.mp.repo_version_match = None  # Unknown
        self.mp.repo_last_activity_at = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        self.mp.repo_stars = 1000  # log10(1000) + 1 = 4
        self.mp.repo_contributors = 100  # log10(100) + 1 = 3

        score = compute_repo_signals_score(self.mp)

        # Expected: 0 (version unknown) +8 (resolved+exists) +2 (present) +6 (recent) +4 (stars) +3 (contributors) = +23
        self.assertEqual(score, 23)

    def test_activity_recency_medium(self):
        """Test medium activity recency (91-365 days)."""
        self.mp.repo_resolved = True
        self.mp.repo_exists = True
        self.mp.repo_last_activity_at = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()

        score = compute_repo_signals_score(self.mp)

        # Expected: +8 (resolved+exists) +3 (medium activity) = +11
        self.assertEqual(score, 11)

    def test_activity_recency_old(self):
        """Test old activity recency (366-730 days)."""
        self.mp.repo_resolved = True
        self.mp.repo_exists = True
        self.mp.repo_last_activity_at = (datetime.now(timezone.utc) - timedelta(days=500)).isoformat()

        score = compute_repo_signals_score(self.mp)

        # Expected: +8 (resolved+exists) +1 (old activity) = +9
        self.assertEqual(score, 9)

    def test_repo_exists_unknown(self):
        """Test repo exists is None (unknown)."""
        self.mp.repo_resolved = True
        self.mp.repo_exists = None  # Unknown
        self.mp.repo_present_in_registry = True

        score = compute_repo_signals_score(self.mp)

        # Expected: +3 (resolved+unknown) +2 (present) = +5
        self.assertEqual(score, 5)

    def test_clamp_minimum(self):
        """Test clamping at minimum value."""
        self.mp.repo_resolved = True
        self.mp.repo_exists = False
        # No other positive signals

        score = compute_repo_signals_score(self.mp)

        # Expected: -5 (resolved+exists=False), should not go below -20
        self.assertEqual(score, -5)

    def test_clamp_maximum(self):
        """Test clamping at maximum value."""
        # Set up maximum positive case
        self.mp.repo_resolved = True
        self.mp.repo_exists = True
        self.mp.repo_present_in_registry = True
        self.mp.repo_version_match = {'matched': True}
        self.mp.repo_last_activity_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        self.mp.repo_stars = 100000  # Very high stars
        self.mp.repo_contributors = 10000  # Very high contributors

        score = compute_repo_signals_score(self.mp)

        # Should be clamped to maximum +30
        self.assertEqual(score, 30)

    def test_malformed_timestamp(self):
        """Test handling of malformed timestamp."""
        self.mp.repo_resolved = True
        self.mp.repo_exists = True
        self.mp.repo_last_activity_at = "invalid-timestamp"

        score = compute_repo_signals_score(self.mp)

        # Expected: +8 (resolved+exists), 0 for activity (malformed)
        self.assertEqual(score, 8)


if __name__ == '__main__':
    unittest.main()
