"""Unit tests for GitHub rate limit configuration and logging."""

import logging
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

from cli_config import apply_github_overrides
from constants import Constants
from common.http_client import _get_on_rate_limit_behavior, robust_get
from common.http_errors import RateLimitExhausted, RetryBudgetExceeded


class TestApplyGitHubOverridesToken(unittest.TestCase):
    """Test cases for GitHub token resolution in apply_github_overrides."""

    def setUp(self):
        """Save original state."""
        self._orig_token = os.environ.get("GITHUB_TOKEN")
        self._orig_rate = getattr(Constants, "GITHUB_ON_RATE_LIMIT", "warn")
        self._orig_per_service = getattr(
            Constants, "HTTP_RATE_POLICY_PER_SERVICE", {}
        ).copy()
        os.environ.pop("GITHUB_TOKEN", None)
        Constants.GITHUB_ON_RATE_LIMIT = "warn"  # type: ignore[attr-defined]

    def tearDown(self):
        """Restore original state."""
        if self._orig_token is not None:
            os.environ["GITHUB_TOKEN"] = self._orig_token
        else:
            os.environ.pop("GITHUB_TOKEN", None)
        Constants.GITHUB_ON_RATE_LIMIT = self._orig_rate  # type: ignore[attr-defined]
        Constants.HTTP_RATE_POLICY_PER_SERVICE = self._orig_per_service  # type: ignore[attr-defined]

    def test_cli_token_sets_env(self):
        """Test that CLI --github-token sets the environment variable."""
        args = MagicMock()
        args.GITHUB_TOKEN = "my_cli_token"
        args.GITHUB_ON_RATE_LIMIT = None
        apply_github_overrides(args)
        self.assertEqual(os.environ.get("GITHUB_TOKEN"), "my_cli_token")

    def test_no_token_leaves_env_unset(self):
        """Test that no CLI token leaves env var unset."""
        args = MagicMock()
        args.GITHUB_TOKEN = None
        args.GITHUB_ON_RATE_LIMIT = None
        apply_github_overrides(args)
        self.assertIsNone(os.environ.get("GITHUB_TOKEN"))


class TestApplyGitHubOverridesStartupMessage(unittest.TestCase):
    """Test cases for GitHub startup messages."""

    def setUp(self):
        """Save original state."""
        self._orig_token = os.environ.get("GITHUB_TOKEN")
        self._orig_rate = getattr(Constants, "GITHUB_ON_RATE_LIMIT", "warn")
        Constants.GITHUB_ON_RATE_LIMIT = "warn"  # type: ignore[attr-defined]

    def tearDown(self):
        """Restore original state."""
        if self._orig_token is not None:
            os.environ["GITHUB_TOKEN"] = self._orig_token
        else:
            os.environ.pop("GITHUB_TOKEN", None)
        Constants.GITHUB_ON_RATE_LIMIT = self._orig_rate  # type: ignore[attr-defined]

    def test_startup_message_with_token(self):
        """Test that startup INFO message is logged when token is set."""
        os.environ["GITHUB_TOKEN"] = "test_token"
        args = MagicMock()
        args.GITHUB_TOKEN = None
        args.GITHUB_ON_RATE_LIMIT = None
        with patch("cli_config.logger") as mock_logger:
            apply_github_overrides(args)
            mock_logger.info.assert_called_once()
            msg = mock_logger.info.call_args[0][0]
            self.assertIn("authenticated API", msg)
            self.assertIn("5,000", msg)

    def test_startup_message_without_token(self):
        """Test that startup INFO message warns when token is NOT set."""
        os.environ.pop("GITHUB_TOKEN", None)
        args = MagicMock()
        args.GITHUB_TOKEN = None
        args.GITHUB_ON_RATE_LIMIT = None
        with patch("cli_config.logger") as mock_logger:
            apply_github_overrides(args)
            mock_logger.info.assert_called_once()
            msg = mock_logger.info.call_args[0][0]
            self.assertIn("not configured", msg)
            self.assertIn("60 requests/hour", msg)


class TestApplyGitHubOverridesRateLimitBehavior(unittest.TestCase):
    """Test cases for GitHub rate limit behavior configuration."""

    def setUp(self):
        """Save original state."""
        self._orig_token = os.environ.get("GITHUB_TOKEN")
        self._orig_rate = getattr(Constants, "GITHUB_ON_RATE_LIMIT", "warn")
        self._orig_per_service = getattr(
            Constants, "HTTP_RATE_POLICY_PER_SERVICE", {}
        ).copy()
        os.environ.pop("GITHUB_TOKEN", None)
        Constants.GITHUB_ON_RATE_LIMIT = "warn"  # type: ignore[attr-defined]

    def tearDown(self):
        """Restore original state."""
        if self._orig_token is not None:
            os.environ["GITHUB_TOKEN"] = self._orig_token
        else:
            os.environ.pop("GITHUB_TOKEN", None)
        Constants.GITHUB_ON_RATE_LIMIT = self._orig_rate  # type: ignore[attr-defined]
        Constants.HTTP_RATE_POLICY_PER_SERVICE = self._orig_per_service  # type: ignore[attr-defined]

    def test_cli_sets_warn(self):
        """Test CLI --github-on-rate-limit=warn sets constant."""
        args = MagicMock()
        args.GITHUB_TOKEN = None
        args.GITHUB_ON_RATE_LIMIT = "warn"
        apply_github_overrides(args)
        self.assertEqual(Constants.GITHUB_ON_RATE_LIMIT, "warn")

    def test_cli_sets_fail(self):
        """Test CLI --github-on-rate-limit=fail sets constant."""
        args = MagicMock()
        args.GITHUB_TOKEN = None
        args.GITHUB_ON_RATE_LIMIT = "fail"
        apply_github_overrides(args)
        self.assertEqual(Constants.GITHUB_ON_RATE_LIMIT, "fail")

    def test_cli_sets_retry(self):
        """Test CLI --github-on-rate-limit=retry sets constant."""
        args = MagicMock()
        args.GITHUB_TOKEN = None
        args.GITHUB_ON_RATE_LIMIT = "retry"
        apply_github_overrides(args)
        self.assertEqual(Constants.GITHUB_ON_RATE_LIMIT, "retry")

    def test_github_per_service_policy_always_present(self):
        """Test that api.github.com per-service policy exists regardless of mode."""
        per_service = getattr(Constants, "HTTP_RATE_POLICY_PER_SERVICE", {})
        self.assertIn("api.github.com", per_service)
        policy = per_service["api.github.com"]
        self.assertEqual(policy["max_retries"], 5)
        self.assertTrue(policy["respect_reset_headers"])
        self.assertEqual(policy["total_retry_time_cap_sec"], 600.0)
        self.assertEqual(policy["max_backoff_sec"], 120.0)

    def test_warn_still_has_per_service_policy(self):
        """Test that api.github.com IS in per-service policy even in warn mode."""
        args = MagicMock()
        args.GITHUB_TOKEN = None
        args.GITHUB_ON_RATE_LIMIT = "warn"
        apply_github_overrides(args)
        per_service = getattr(Constants, "HTTP_RATE_POLICY_PER_SERVICE", {})
        self.assertIn("api.github.com", per_service)
        policy = per_service["api.github.com"]
        self.assertEqual(policy["max_retries"], 5)

    def test_none_cli_arg_preserves_default(self):
        """Test that None CLI arg preserves the default constant value."""
        Constants.GITHUB_ON_RATE_LIMIT = "warn"  # type: ignore[attr-defined]
        args = MagicMock()
        args.GITHUB_TOKEN = None
        args.GITHUB_ON_RATE_LIMIT = None
        apply_github_overrides(args)
        self.assertEqual(Constants.GITHUB_ON_RATE_LIMIT, "warn")


class TestGetOnRateLimitBehavior(unittest.TestCase):
    """Test cases for _get_on_rate_limit_behavior helper."""

    def setUp(self):
        self._orig_rate = getattr(Constants, "GITHUB_ON_RATE_LIMIT", "warn")

    def tearDown(self):
        Constants.GITHUB_ON_RATE_LIMIT = self._orig_rate  # type: ignore[attr-defined]

    def test_github_service_returns_constant(self):
        """Test that api.github.com returns the configured constant."""
        Constants.GITHUB_ON_RATE_LIMIT = "fail"  # type: ignore[attr-defined]
        self.assertEqual(_get_on_rate_limit_behavior("api.github.com"), "fail")

    def test_other_service_returns_warn(self):
        """Test that non-GitHub services always return 'warn'."""
        Constants.GITHUB_ON_RATE_LIMIT = "fail"  # type: ignore[attr-defined]
        self.assertEqual(_get_on_rate_limit_behavior("pypi.org"), "warn")

    def test_unknown_service_returns_warn(self):
        """Test that unknown/empty services return 'warn'."""
        self.assertEqual(_get_on_rate_limit_behavior(""), "warn")
        self.assertEqual(_get_on_rate_limit_behavior("unknown"), "warn")


class TestRobustGetRateLimitLogging(unittest.TestCase):
    """Test cases for rate limit logging in robust_get."""

    def setUp(self):
        self._orig_rate = getattr(Constants, "GITHUB_ON_RATE_LIMIT", "warn")

    def tearDown(self):
        Constants.GITHUB_ON_RATE_LIMIT = self._orig_rate  # type: ignore[attr-defined]

    @patch("common.http_client.middleware_request")
    def test_rate_limit_logs_warning(self, mock_request):
        """Test that rate limit exceptions produce a WARNING log."""
        mock_request.side_effect = RateLimitExhausted(
            service="api.github.com",
            method="GET",
            url="https://api.github.com/repos/test/repo",
            attempts=1,
            reason="Rate limit exceeded",
            last_status=429,
        )
        Constants.GITHUB_ON_RATE_LIMIT = "warn"  # type: ignore[attr-defined]
        with patch("common.http_client.logger") as mock_logger:
            status, _, body = robust_get(
                "https://api.github.com/repos/test/repo",
                headers={"Accept": "application/json"},
            )
            self.assertEqual(status, 0)
            self.assertIn("Rate limit exhausted", body)
            mock_logger.warning.assert_called()

    @patch("common.http_client.middleware_request")
    def test_rate_limit_fail_exits(self, mock_request):
        """Test that fail mode calls sys.exit on rate limit."""
        mock_request.side_effect = RateLimitExhausted(
            service="api.github.com",
            method="GET",
            url="https://api.github.com/repos/test/repo",
            attempts=1,
            reason="Rate limit exceeded",
            last_status=429,
        )
        Constants.GITHUB_ON_RATE_LIMIT = "fail"  # type: ignore[attr-defined]
        with patch("common.http_client.sys.exit") as mock_exit:
            robust_get(
                "https://api.github.com/repos/test/repo",
                headers={"Accept": "application/json"},
            )
            mock_exit.assert_called_once_with(2)  # ExitCodes.CONNECTION_ERROR

    @patch("common.http_client.middleware_request")
    def test_retry_budget_exceeded_logs_warning(self, mock_request):
        """Test that RetryBudgetExceeded exceptions produce a WARNING log."""
        mock_request.side_effect = RetryBudgetExceeded(
            service="api.github.com",
            method="GET",
            url="https://api.github.com/repos/test/repo",
            attempt=3,
            computed_wait=120.0,
            remaining_budget=10.0,
            reason="Budget exceeded",
        )
        Constants.GITHUB_ON_RATE_LIMIT = "warn"  # type: ignore[attr-defined]
        with patch("common.http_client.logger") as mock_logger:
            status, _, body = robust_get(
                "https://api.github.com/repos/test/repo",
                headers={"Accept": "application/json"},
            )
            self.assertEqual(status, 0)
            mock_logger.warning.assert_called()

    @patch("common.http_client.middleware_request")
    def test_non_github_rate_limit_always_warns(self, mock_request):
        """Test that non-GitHub rate limits always use warn behavior."""
        mock_request.side_effect = RateLimitExhausted(
            service="pypi.org",
            method="GET",
            url="https://pypi.org/pypi/requests/json",
            attempts=1,
            reason="Rate limit exceeded",
            last_status=429,
        )
        Constants.GITHUB_ON_RATE_LIMIT = "fail"  # type: ignore[attr-defined]
        with patch("common.http_client.logger") as mock_logger:
            status, _, body = robust_get(
                "https://pypi.org/pypi/requests/json",
                headers={"Accept": "application/json"},
            )
            self.assertEqual(status, 0)
            self.assertIn("Rate limit exhausted", body)
            mock_logger.warning.assert_called()


class TestConstantsYAMLGitHub(unittest.TestCase):
    """Test YAML config loading for GitHub section."""

    def setUp(self):
        self._orig_rate = getattr(Constants, "GITHUB_ON_RATE_LIMIT", "warn")

    def tearDown(self):
        Constants.GITHUB_ON_RATE_LIMIT = self._orig_rate  # type: ignore[attr-defined]

    def test_yaml_github_on_rate_limit(self):
        """Test that _apply_config_overrides handles github.on_rate_limit."""
        from constants import _apply_config_overrides
        Constants.GITHUB_ON_RATE_LIMIT = "warn"  # type: ignore[attr-defined]
        _apply_config_overrides({"github": {"on_rate_limit": "fail"}})
        self.assertEqual(Constants.GITHUB_ON_RATE_LIMIT, "fail")

    def test_yaml_github_on_rate_limit_invalid(self):
        """Test that invalid on_rate_limit values are ignored."""
        from constants import _apply_config_overrides
        Constants.GITHUB_ON_RATE_LIMIT = "warn"  # type: ignore[attr-defined]
        _apply_config_overrides({"github": {"on_rate_limit": "invalid"}})
        self.assertEqual(Constants.GITHUB_ON_RATE_LIMIT, "warn")

    def test_yaml_github_empty_section(self):
        """Test that empty github section does not change defaults."""
        from constants import _apply_config_overrides
        Constants.GITHUB_ON_RATE_LIMIT = "warn"  # type: ignore[attr-defined]
        _apply_config_overrides({"github": {}})
        self.assertEqual(Constants.GITHUB_ON_RATE_LIMIT, "warn")


class TestConstantsEnvGitHub(unittest.TestCase):
    """Test environment variable overrides for GitHub settings."""

    def setUp(self):
        self._orig_rate = getattr(Constants, "GITHUB_ON_RATE_LIMIT", "warn")
        os.environ.pop("DEPGATE_GITHUB_ON_RATE_LIMIT", None)

    def tearDown(self):
        Constants.GITHUB_ON_RATE_LIMIT = self._orig_rate  # type: ignore[attr-defined]
        os.environ.pop("DEPGATE_GITHUB_ON_RATE_LIMIT", None)

    def test_env_override_sets_constant(self):
        """Test that DEPGATE_GITHUB_ON_RATE_LIMIT env var sets the constant."""
        from constants import _apply_env_overrides
        os.environ["DEPGATE_GITHUB_ON_RATE_LIMIT"] = "retry"
        _apply_env_overrides()
        self.assertEqual(Constants.GITHUB_ON_RATE_LIMIT, "retry")

    def test_env_override_invalid_ignored(self):
        """Test that invalid env var values are ignored."""
        from constants import _apply_env_overrides
        Constants.GITHUB_ON_RATE_LIMIT = "warn"  # type: ignore[attr-defined]
        os.environ["DEPGATE_GITHUB_ON_RATE_LIMIT"] = "bogus"
        _apply_env_overrides()
        self.assertEqual(Constants.GITHUB_ON_RATE_LIMIT, "warn")


class TestGitHubClientLogging(unittest.TestCase):
    """Test that GitHubClient logs warnings on non-200 responses."""

    @patch("repository.github.get_json")
    def test_get_repo_403_logs_warning(self, mock_get_json):
        """Test that get_repo logs WARNING on 403 response."""
        mock_get_json.return_value = (403, {}, None)
        from repository.github import GitHubClient
        client = GitHubClient(token="fake")
        with patch("repository.github.logger") as mock_logger:
            result = client.get_repo("owner", "repo")
            self.assertIsNone(result)
            mock_logger.warning.assert_called_once()
            msg = mock_logger.warning.call_args[0][0]
            self.assertIn("rate limited", msg)

    @patch("repository.github.get_json")
    def test_get_repo_429_logs_warning(self, mock_get_json):
        """Test that get_repo logs WARNING on 429 response."""
        mock_get_json.return_value = (429, {}, None)
        from repository.github import GitHubClient
        client = GitHubClient(token="fake")
        with patch("repository.github.logger") as mock_logger:
            result = client.get_repo("owner", "repo")
            self.assertIsNone(result)
            mock_logger.warning.assert_called_once()

    @patch("repository.github.get_json")
    def test_get_repo_404_logs_warning(self, mock_get_json):
        """Test that get_repo logs WARNING on 404 response."""
        mock_get_json.return_value = (404, {}, None)
        from repository.github import GitHubClient
        client = GitHubClient(token="fake")
        with patch("repository.github.logger") as mock_logger:
            result = client.get_repo("owner", "repo")
            self.assertIsNone(result)
            mock_logger.warning.assert_called_once()
            msg = mock_logger.warning.call_args[0][0]
            self.assertIn("HTTP %s", msg)

    @patch("repository.github.get_json")
    def test_get_repo_status_0_no_warning(self, mock_get_json):
        """Test that get_repo does NOT log on status 0 (already logged by robust_get)."""
        mock_get_json.return_value = (0, {}, None)
        from repository.github import GitHubClient
        client = GitHubClient(token="fake")
        with patch("repository.github.logger") as mock_logger:
            result = client.get_repo("owner", "repo")
            self.assertIsNone(result)
            mock_logger.warning.assert_not_called()

    @patch("repository.github.get_json")
    def test_get_contributors_count_403_logs_warning(self, mock_get_json):
        """Test that get_contributors_count logs WARNING on 403."""
        mock_get_json.return_value = (403, {}, None)
        from repository.github import GitHubClient
        client = GitHubClient(token="fake")
        with patch("repository.github.logger") as mock_logger:
            result = client.get_contributors_count("owner", "repo")
            self.assertIsNone(result)
            mock_logger.warning.assert_called_once()


class TestReadTheDocsDefaultPolicy(unittest.TestCase):
    """Test cases for ReadTheDocs default per-service rate policy."""

    def setUp(self):
        """Save original state."""
        self._orig_per_service = getattr(
            Constants, "HTTP_RATE_POLICY_PER_SERVICE", {}
        ).copy()

    def tearDown(self):
        """Restore original state."""
        Constants.HTTP_RATE_POLICY_PER_SERVICE = self._orig_per_service  # type: ignore[attr-defined]

    def test_rtd_per_service_policy_present(self):
        """Test that readthedocs.org per-service policy exists with correct defaults."""
        per_service = getattr(Constants, "HTTP_RATE_POLICY_PER_SERVICE", {})
        self.assertIn("readthedocs.org", per_service)
        policy = per_service["readthedocs.org"]
        self.assertEqual(policy["max_retries"], 5)
        self.assertEqual(policy["initial_backoff_sec"], 2.0)
        self.assertEqual(policy["multiplier"], 2.0)
        self.assertEqual(policy["max_backoff_sec"], 30.0)
        self.assertEqual(policy["total_retry_time_cap_sec"], 120.0)
        self.assertTrue(policy["respect_retry_after"])
        self.assertEqual(policy["strategy"], "exponential_jitter")

    def test_rtd_policy_overridable_by_yaml(self):
        """Test that YAML per-service config for readthedocs.org takes precedence."""
        from constants import _apply_config_overrides
        _apply_config_overrides({
            "http": {
                "rate_policy": {
                    "per_service": {
                        "readthedocs.org": {
                            "max_retries": 10,
                            "strategy": "fixed",
                        }
                    }
                }
            }
        })
        per_service = getattr(Constants, "HTTP_RATE_POLICY_PER_SERVICE", {})
        self.assertIn("readthedocs.org", per_service)
        policy = per_service["readthedocs.org"]
        self.assertEqual(policy["max_retries"], 10)
        self.assertEqual(policy["strategy"], "fixed")


if __name__ == "__main__":
    unittest.main()
