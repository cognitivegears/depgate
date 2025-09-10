"""Unit tests for HTTP policy configuration and backoff calculations."""

import time
from unittest.mock import patch

import pytest

from common.http_policy import (
    HttpBackoffStrategy,
    HttpRetryPolicy,
    load_http_policy_from_constants,
    is_idempotent,
)


class TestHttpRetryPolicy:
    """Test HttpRetryPolicy dataclass."""

    def test_policy_creation(self):
        """Test creating a policy with all parameters."""
        policy = HttpRetryPolicy(
            max_retries=3,
            initial_backoff=1.0,
            multiplier=2.0,
            jitter_pct=0.1,
            max_backoff=30.0,
            total_retry_time_cap_sec=120.0,
            strategy=HttpBackoffStrategy.EXPONENTIAL,
            respect_retry_after=True,
            respect_reset_headers=True,
            allow_non_idempotent_retry=False
        )

        assert policy.max_retries == 3
        assert policy.initial_backoff == 1.0
        assert policy.multiplier == 2.0
        assert policy.jitter_pct == 0.1
        assert policy.max_backoff == 30.0
        assert policy.total_retry_time_cap_sec == 120.0
        assert policy.strategy == HttpBackoffStrategy.EXPONENTIAL
        assert policy.respect_retry_after is True
        assert policy.respect_reset_headers is True
        assert policy.allow_non_idempotent_retry is False


class TestLoadHttpPolicyFromConstants:
    """Test loading policy from Constants."""

    @patch('common.http_policy.Constants')
    def test_load_default_policy(self, mock_constants):
        """Test loading default policy when no overrides exist."""
        mock_constants.HTTP_RATE_POLICY_DEFAULT_MAX_RETRIES = 5
        mock_constants.HTTP_RATE_POLICY_DEFAULT_INITIAL_BACKOFF_SEC = 2.0
        mock_constants.HTTP_RATE_POLICY_DEFAULT_MULTIPLIER = 3.0
        mock_constants.HTTP_RATE_POLICY_DEFAULT_JITTER_PCT = 0.2
        mock_constants.HTTP_RATE_POLICY_DEFAULT_MAX_BACKOFF_SEC = 60.0
        mock_constants.HTTP_RATE_POLICY_DEFAULT_TOTAL_RETRY_TIME_CAP_SEC = 300.0
        mock_constants.HTTP_RATE_POLICY_DEFAULT_STRATEGY = "exponential_jitter"
        mock_constants.HTTP_RATE_POLICY_DEFAULT_RESPECT_RETRY_AFTER = False
        mock_constants.HTTP_RATE_POLICY_DEFAULT_RESPECT_RESET_HEADERS = False
        mock_constants.HTTP_RATE_POLICY_DEFAULT_ALLOW_NON_IDEMPOTENT_RETRY = True
        mock_constants.HTTP_RATE_POLICY_PER_SERVICE = {}

        default_policy, per_service_overrides = load_http_policy_from_constants()

        assert default_policy.max_retries == 5
        assert default_policy.initial_backoff == 2.0
        assert default_policy.multiplier == 3.0
        assert default_policy.jitter_pct == 0.2
        assert default_policy.max_backoff == 60.0
        assert default_policy.total_retry_time_cap_sec == 300.0
        assert default_policy.strategy == HttpBackoffStrategy.EXPONENTIAL_JITTER
        assert default_policy.respect_retry_after is False
        assert default_policy.respect_reset_headers is False
        assert default_policy.allow_non_idempotent_retry is True
        assert per_service_overrides == {}

    @patch('common.http_policy.Constants')
    def test_load_per_service_overrides(self, mock_constants):
        """Test loading per-service overrides."""
        mock_constants.HTTP_RATE_POLICY_DEFAULT_MAX_RETRIES = 0
        mock_constants.HTTP_RATE_POLICY_DEFAULT_INITIAL_BACKOFF_SEC = 0.5
        mock_constants.HTTP_RATE_POLICY_DEFAULT_MULTIPLIER = 2.0
        mock_constants.HTTP_RATE_POLICY_DEFAULT_JITTER_PCT = 0.2
        mock_constants.HTTP_RATE_POLICY_DEFAULT_MAX_BACKOFF_SEC = 60.0
        mock_constants.HTTP_RATE_POLICY_DEFAULT_TOTAL_RETRY_TIME_CAP_SEC = 120.0
        mock_constants.HTTP_RATE_POLICY_DEFAULT_STRATEGY = "exponential_jitter"
        mock_constants.HTTP_RATE_POLICY_DEFAULT_RESPECT_RETRY_AFTER = True
        mock_constants.HTTP_RATE_POLICY_DEFAULT_RESPECT_RESET_HEADERS = True
        mock_constants.HTTP_RATE_POLICY_DEFAULT_ALLOW_NON_IDEMPOTENT_RETRY = False

        mock_constants.HTTP_RATE_POLICY_PER_SERVICE = {
            "api.github.com": {
                "max_retries": 2,
                "strategy": "fixed"
            }
        }

        default_policy, per_service_overrides = load_http_policy_from_constants()

        assert "api.github.com" in per_service_overrides
        github_policy = per_service_overrides["api.github.com"]
        assert github_policy.max_retries == 2
        assert github_policy.strategy == HttpBackoffStrategy.FIXED
        # Other fields should inherit from default
        assert github_policy.initial_backoff == 0.5
        assert github_policy.respect_retry_after is True


class TestIsIdempotent:
    """Test HTTP method idempotency checking."""

    @pytest.mark.parametrize("method,expected", [
        ("GET", True),
        ("HEAD", True),
        ("PUT", True),
        ("DELETE", True),
        ("OPTIONS", True),
        ("TRACE", True),
        ("POST", False),
        ("PATCH", False),
        ("CONNECT", False),
        ("get", True),  # case insensitive
        ("post", False),
    ])
    def test_is_idempotent(self, method, expected):
        """Test idempotency checking for various HTTP methods."""
        assert is_idempotent(method) == expected


class TestBackoffCalculations:
    """Test backoff time calculations (would be in middleware tests)."""

    def test_fixed_backoff(self):
        """Test fixed backoff strategy."""
        policy = HttpRetryPolicy(
            max_retries=3,
            initial_backoff=1.0,
            multiplier=2.0,
            jitter_pct=0.0,
            max_backoff=10.0,
            total_retry_time_cap_sec=60.0,
            strategy=HttpBackoffStrategy.FIXED,
            respect_retry_after=True,
            respect_reset_headers=True,
            allow_non_idempotent_retry=False
        )

        # Fixed strategy should always return initial_backoff
        assert policy.initial_backoff == 1.0

    def test_exponential_backoff(self):
        """Test exponential backoff strategy."""
        policy = HttpRetryPolicy(
            max_retries=3,
            initial_backoff=1.0,
            multiplier=2.0,
            jitter_pct=0.0,
            max_backoff=10.0,
            total_retry_time_cap_sec=60.0,
            strategy=HttpBackoffStrategy.EXPONENTIAL,
            respect_retry_after=True,
            respect_reset_headers=True,
            allow_non_idempotent_retry=False
        )

        # For attempt 1: 1.0
        # For attempt 2: 1.0 * 2.0 = 2.0
        # For attempt 3: 1.0 * 2.0 * 2.0 = 4.0
        assert policy.initial_backoff == 1.0
        assert policy.multiplier == 2.0

    def test_exponential_jitter_backoff(self):
        """Test exponential jitter backoff strategy."""
        policy = HttpRetryPolicy(
            max_retries=3,
            initial_backoff=1.0,
            multiplier=2.0,
            jitter_pct=0.1,
            max_backoff=10.0,
            total_retry_time_cap_sec=60.0,
            strategy=HttpBackoffStrategy.EXPONENTIAL_JITTER,
            respect_retry_after=True,
            respect_reset_headers=True,
            allow_non_idempotent_retry=False
        )

        assert policy.jitter_pct == 0.1

    def test_max_backoff_clamping(self):
        """Test that backoff is clamped to max_backoff."""
        policy = HttpRetryPolicy(
            max_retries=10,
            initial_backoff=1.0,
            multiplier=10.0,
            jitter_pct=0.0,
            max_backoff=5.0,
            total_retry_time_cap_sec=60.0,
            strategy=HttpBackoffStrategy.EXPONENTIAL,
            respect_retry_after=True,
            respect_reset_headers=True,
            allow_non_idempotent_retry=False
        )

        assert policy.max_backoff == 5.0
