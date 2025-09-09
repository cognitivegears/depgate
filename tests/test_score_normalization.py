from datetime import datetime, timezone, timedelta

import pytest

from analysis.heuristics import (
    _clamp01,
    _norm_base_score,
    _norm_repo_stars,
    _norm_repo_contributors,
    _norm_repo_last_activity,
    _norm_version_match,
    compute_final_score,
)
from metapackage import MetaPackage


class TestNormalization:
    def test_clamp01_bounds(self):
        assert _clamp01(-1.0) == 0.0
        assert _clamp01(0.0) == 0.0
        assert _clamp01(0.5) == 0.5
        assert _clamp01(1.0) == 1.0
        assert _clamp01(2.0) == 1.0

    def test_norm_base_score(self):
        assert _norm_base_score(None) is None
        assert _norm_base_score(0.5) == 0.5
        assert _norm_base_score(2.0) == 1.0
        assert _norm_base_score(-1.0) == 0.0

    def test_norm_repo_stars(self):
        # 0 stars -> 0.0
        assert _norm_repo_stars(0) == 0.0
        # Negative treated as 0
        assert _norm_repo_stars(-10) == 0.0
        # Around 1k stars -> saturated near 1.0
        val = _norm_repo_stars(1000)
        assert val is not None and 0.99 <= val <= 1.0
        # Very large stars -> 1.0
        assert _norm_repo_stars(10_000_000) == 1.0
        # None -> missing
        assert _norm_repo_stars(None) is None

    def test_norm_repo_contributors(self):
        assert _norm_repo_contributors(0) == 0.0
        assert _norm_repo_contributors(25) == 0.5
        assert _norm_repo_contributors(50) == 1.0
        assert _norm_repo_contributors(500) == 1.0
        assert _norm_repo_contributors(-5) == 0.0
        assert _norm_repo_contributors(None) is None

    def test_norm_repo_last_activity(self):
        now_iso = datetime.now(timezone.utc).isoformat()
        d200_iso = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
        d400_iso = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
        d1000_iso = (datetime.now(timezone.utc) - timedelta(days=1000)).isoformat()

        assert _norm_repo_last_activity(now_iso) == 1.0
        assert _norm_repo_last_activity(d200_iso) == 0.6
        assert _norm_repo_last_activity(d400_iso) == 0.3
        assert _norm_repo_last_activity(d1000_iso) == 0.0
        assert _norm_repo_last_activity("not-a-timestamp") is None
        assert _norm_repo_last_activity(None) is None

    def test_norm_version_match(self):
        assert _norm_version_match(None) is None
        assert _norm_version_match({"matched": True}) == 1.0
        assert _norm_version_match({"matched": False}) == 0.0


class TestFinalScore:
    def make_pkg(self) -> MetaPackage:
        mp = MetaPackage("pkg")
        mp.exists = True
        return mp

    def test_compute_final_only_base(self):
        mp = self.make_pkg()
        mp.score = 0.5
        final, breakdown, weights = compute_final_score(mp)
        assert 0.0 <= final <= 1.0
        assert pytest.approx(final, rel=1e-6) == 0.5
        assert "base_score" in breakdown
        assert "base_score" in weights and 0.99 <= sum(weights.values()) <= 1.01

    def test_compute_final_missing_metrics_weight_renormalization(self):
        # Only stars and present_in_registry are present
        mp = self.make_pkg()
        mp.score = None
        mp.repo_stars = 1000   # saturates to 1.0
        mp.repo_contributors = None
        mp.repo_last_activity_at = None
        mp.repo_present_in_registry = True
        mp.repo_version_match = None

        final, breakdown, weights = compute_final_score(mp)
        # Only two weights: stars (0.15) and present (0.05) -> renormalize to 0.75 and 0.25
        assert set(weights.keys()) == {"repo_stars", "repo_present_in_registry"}
        assert pytest.approx(weights["repo_stars"] + weights["repo_present_in_registry"], rel=1e-6) == 1.0
        # Both components normalized to 1 -> final must be ~1 (allow tiny fp error)
        assert pytest.approx(final, rel=1e-12) == 1.0

    def test_compute_final_all_extreme_inputs_clamped(self):
        mp = self.make_pkg()
        mp.score = 2.0  # should clamp to 1.0
        mp.repo_stars = 10_000_000
        mp.repo_contributors = 10_000
        mp.repo_last_activity_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        mp.repo_present_in_registry = True
        mp.repo_version_match = {"matched": True}

        final, breakdown, weights = compute_final_score(mp)
        assert 0.0 <= final <= 1.0
        assert final == 1.0

    def test_compute_final_handles_nones(self):
        mp = self.make_pkg()
        # leave everything None except one signal
        mp.repo_contributors = 10  # 0.2
        final, breakdown, weights = compute_final_score(mp)
        assert 0.19 <= final <= 0.21
        assert set(weights.keys()) == {"repo_contributors"}
