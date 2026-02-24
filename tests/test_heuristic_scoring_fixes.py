"""Tests for heuristic scoring fixes: weekly downloads, rebalanced weights, proactive throttling."""

import math
import time
from unittest.mock import patch

from analysis.heuristics import (
    _norm_weekly_downloads,
    compute_final_score,
)
from common.http_rate_middleware import (
    _apply_proactive_throttle,
    _get_service_cooldown,
    _clear_service_cooldown,
)
from constants import Constants
from metapackage import MetaPackage


class TestNormWeeklyDownloads:
    def setup_method(self):
        MetaPackage.instances.clear()

    def test_none_returns_none(self):
        assert _norm_weekly_downloads(None) is None

    def test_zero_downloads(self):
        result = _norm_weekly_downloads(0)
        assert result == 0.0

    def test_one_download(self):
        result = _norm_weekly_downloads(1)
        # log10(2)/6 ≈ 0.05
        assert 0.04 < result < 0.06

    def test_thousand_downloads(self):
        result = _norm_weekly_downloads(1000)
        # log10(1001)/6 ≈ 0.5
        assert 0.49 < result < 0.51

    def test_million_downloads_saturates(self):
        result = _norm_weekly_downloads(1_000_000)
        # log10(1_000_001)/6 ≈ 1.0
        assert result == 1.0

    def test_ten_million_clamped_to_one(self):
        result = _norm_weekly_downloads(10_000_000)
        assert result == 1.0

    def test_negative_treated_as_zero(self):
        result = _norm_weekly_downloads(-100)
        assert result == 0.0

    def test_non_numeric_returns_none(self):
        assert _norm_weekly_downloads("not a number") is None


class TestRebalancedWeights:
    def setup_method(self):
        MetaPackage.instances.clear()

    def test_default_weights_include_weekly_downloads(self):
        assert "weekly_downloads" in Constants.HEURISTICS_WEIGHTS_DEFAULT
        assert Constants.HEURISTICS_WEIGHTS_DEFAULT["weekly_downloads"] == 0.12

    def test_default_weights_sum_close_to_one(self):
        total = sum(Constants.HEURISTICS_WEIGHTS_DEFAULT.values())
        assert abs(total - 0.95) < 0.01

    def test_compute_final_score_uses_weekly_downloads(self):
        mp = MetaPackage("pkg", "pypi")
        mp.exists = True
        mp.weekly_downloads = 100_000
        mp.repo_version_match = {"matched": True}
        mp.repo_stars = 500
        mp.repo_contributors = 20
        mp.repo_last_activity_at = "2025-01-01T00:00:00Z"
        mp.repo_present_in_registry = True
        mp.trust_score = 0.5

        score, breakdown, weights_used = compute_final_score(mp)

        assert "weekly_downloads" in breakdown
        assert breakdown["weekly_downloads"]["raw"] == 100_000
        assert breakdown["weekly_downloads"]["normalized"] is not None
        assert "weekly_downloads" in weights_used
        assert score > 0.0

    def test_pypi_without_base_score_still_scores_well(self):
        """PyPI packages (no base_score) with good signals should score well."""
        mp = MetaPackage("requests", "pypi")
        mp.exists = True
        mp.weekly_downloads = 5_000_000
        mp.repo_version_match = {"matched": True}
        mp.repo_stars = 10000
        mp.repo_contributors = 100
        mp.repo_last_activity_at = "2025-12-01T00:00:00Z"
        mp.repo_present_in_registry = True
        mp.trust_score = 0.5

        score, breakdown, weights_used = compute_final_score(mp)

        # A well-known package should score well above 0.6
        assert score > 0.6


class TestProactiveGitHubThrottle:
    def setup_method(self):
        MetaPackage.instances.clear()
        _clear_service_cooldown("api.github.com")

    def teardown_method(self):
        _clear_service_cooldown("api.github.com")

    def test_sets_cooldown_from_rate_headers(self):
        now = time.time()
        reset_ts = now + 3600  # 1 hour from now
        headers = {
            "X-RateLimit-Remaining": "100",
            "X-RateLimit-Reset": str(reset_ts),
        }

        _apply_proactive_throttle("api.github.com", headers)

        cooldown = _get_service_cooldown("api.github.com")
        # Delay should be roughly 3600/100 = 36 seconds
        expected_delay = 3600 / 100
        assert cooldown > now
        assert abs((cooldown - now) - expected_delay) < 2.0

    def test_no_cooldown_when_headers_missing(self):
        _apply_proactive_throttle("api.github.com", {})
        assert _get_service_cooldown("api.github.com") == 0

    def test_no_cooldown_when_remaining_zero(self):
        now = time.time()
        headers = {
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(now + 3600),
        }
        _apply_proactive_throttle("api.github.com", headers)
        # remaining <= 0, should not set proactive cooldown
        assert _get_service_cooldown("api.github.com") == 0

    def test_high_remaining_gives_small_delay(self):
        now = time.time()
        headers = {
            "X-RateLimit-Remaining": "4999",
            "X-RateLimit-Reset": str(now + 3600),
        }
        _apply_proactive_throttle("api.github.com", headers)
        cooldown = _get_service_cooldown("api.github.com")
        delay = cooldown - now
        # 3600/4999 ≈ 0.72 seconds
        assert delay < 1.0

    def test_low_remaining_gives_large_delay(self):
        now = time.time()
        headers = {
            "X-RateLimit-Remaining": "5",
            "X-RateLimit-Reset": str(now + 300),
        }
        _apply_proactive_throttle("api.github.com", headers)
        cooldown = _get_service_cooldown("api.github.com")
        delay = cooldown - now
        # 300/5 = 60 seconds
        assert abs(delay - 60.0) < 2.0

    def test_skips_proactive_throttle_when_delay_exceeds_cap(self):
        now = time.time()
        headers = {
            "X-RateLimit-Remaining": "5",
            "X-RateLimit-Reset": str(now + 300),
        }
        _apply_proactive_throttle("api.github.com", headers, max_delay_sec=10.0)
        assert _get_service_cooldown("api.github.com") == 0
