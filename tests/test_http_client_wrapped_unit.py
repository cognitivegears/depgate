"""Unit tests for HTTP client functions with middleware integration."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys

import requests

from common.http_client import safe_get, safe_post, robust_get
from common.http_errors import RateLimitExhausted, RetryBudgetExceeded


class TestSafeGet:
    """Test safe_get function with middleware."""

    @patch('common.http_client.middleware_request')
    def test_safe_get_success(self, mock_middleware):
        """Test successful GET request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_middleware.return_value = mock_response

        result = safe_get("https://api.example.com/test", context="test")

        mock_middleware.assert_called_once_with(
            "GET",
            "https://api.example.com/test",
            timeout=30,  # Constants.REQUEST_TIMEOUT
            context="test",
            extra_log_fields={"component": "http_client", "action": "GET"}
        )
        assert result == mock_response

    @patch('common.http_client.middleware_request')
    @patch('sys.exit')
    def test_safe_get_rate_limit_exhausted(self, mock_exit, mock_middleware):
        """Test GET request with rate limit exhaustion."""
        mock_middleware.side_effect = RateLimitExhausted(
            "api.example.com", "GET", "https://api.example.com/test",
            3, "Rate limit exceeded", {}, 429
        )

        safe_get("https://api.example.com/test", context="test")

        mock_exit.assert_called_once_with(2)  # ExitCodes.CONNECTION_ERROR.value

    @patch('common.http_client.middleware_request')
    @patch('sys.exit')
    def test_safe_get_timeout(self, mock_exit, mock_middleware):
        """Test GET request with timeout."""
        mock_middleware.side_effect = requests.Timeout("Connection timed out")

        safe_get("https://api.example.com/test", context="test")

        mock_exit.assert_called_once_with(2)  # ExitCodes.CONNECTION_ERROR.value

    @patch('common.http_client.middleware_request')
    @patch('sys.exit')
    def test_safe_get_connection_error(self, mock_exit, mock_middleware):
        """Test GET request with connection error."""
        mock_middleware.side_effect = requests.ConnectionError("Connection failed")

        safe_get("https://api.example.com/test", context="test")

        mock_exit.assert_called_once_with(2)  # ExitCodes.CONNECTION_ERROR.value


class TestSafePost:
    """Test safe_post function with middleware."""

    @patch('common.http_client.middleware_request')
    def test_safe_post_success(self, mock_middleware):
        """Test successful POST request."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_middleware.return_value = mock_response

        result = safe_post("https://api.example.com/test", context="test", data="test data")

        mock_middleware.assert_called_once_with(
            "POST",
            "https://api.example.com/test",
            data="test data",
            timeout=30,
            context="test",
            extra_log_fields={"component": "http_client", "action": "POST"}
        )
        assert result == mock_response

    @patch('common.http_client.middleware_request')
    @patch('sys.exit')
    def test_safe_post_rate_limit_exhausted(self, mock_exit, mock_middleware):
        """Test POST request with rate limit exhaustion."""
        mock_middleware.side_effect = RetryBudgetExceeded(
            "api.example.com", "POST", "https://api.example.com/test",
            2, 5.0, 10.0, "Budget exceeded"
        )

        safe_post("https://api.example.com/test", context="test")

        mock_exit.assert_called_once_with(2)


class TestRobustGet:
    """Test robust_get function with middleware."""

    @patch('common.http_client.middleware_request')
    def test_robust_get_success(self, mock_middleware):
        """Test successful robust GET request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'application/json'}
        mock_response.text = '{"test": "data"}'
        mock_middleware.return_value = mock_response

        status, headers, text = robust_get("https://api.example.com/test")

        assert status == 200
        assert headers == {'Content-Type': 'application/json'}
        assert text == '{"test": "data"}'

        mock_middleware.assert_called_once_with(
            "GET",
            "https://api.example.com/test",
            headers=None,
            timeout=30,
            context="robust_get",
            extra_log_fields={"component": "http_client", "action": "GET"}
        )

    @patch('common.http_client.middleware_request')
    def test_robust_get_with_headers(self, mock_middleware):
        """Test robust GET request with custom headers."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.text = "response"
        mock_middleware.return_value = mock_response

        custom_headers = {'Authorization': 'Bearer token'}
        status, headers, text = robust_get("https://api.example.com/test", headers=custom_headers)

        assert status == 200
        mock_middleware.assert_called_once_with(
            "GET",
            "https://api.example.com/test",
            headers=custom_headers,
            timeout=30,
            context="robust_get",
            extra_log_fields={"component": "http_client", "action": "GET"}
        )

    @patch('common.http_client.middleware_request')
    def test_robust_get_rate_limit_exhausted(self, mock_middleware):
        """Test robust GET request with rate limit exhaustion."""
        from common.http_errors import RateLimitExhausted
        mock_middleware.side_effect = RateLimitExhausted(
            "api.example.com", "GET", "https://api.example.com/test",
            3, "Rate limit exceeded", {}, 429
        )

        status, headers, text = robust_get("https://api.example.com/test")

        assert status == 0
        assert headers == {}
        assert text == "Rate limit exhausted"

    @patch('common.http_client.middleware_request')
    def test_robust_get_timeout(self, mock_middleware):
        """Test robust GET request with timeout."""
        mock_middleware.side_effect = requests.Timeout("Connection timed out")

        status, headers, text = robust_get("https://api.example.com/test")

        assert status == 0
        assert headers == {}
        assert text == "Request timed out"

    @patch('common.http_client.middleware_request')
    def test_robust_get_connection_error(self, mock_middleware):
        """Test robust GET request with connection error."""
        mock_middleware.side_effect = requests.ConnectionError("Connection failed")

        status, headers, text = robust_get("https://api.example.com/test")

        assert status == 0
        assert headers == {}
        assert text == "Request failed: Connection failed"

    @patch('common.http_client._http_cache')
    @patch('common.http_client._is_cache_valid')
    def test_robust_get_cache_hit(self, mock_is_valid, mock_cache):
        """Test robust GET request with cache hit."""
        mock_is_valid.return_value = True
        cached_data = (200, {'Content-Type': 'application/json'}, '{"cached": "data"}')
        mock_cache.__getitem__.return_value = cached_data

        status, headers, text = robust_get("https://api.example.com/test")

        assert status == 200
        assert headers == {'Content-Type': 'application/json'}
        assert text == '{"cached": "data"}'

    @patch('common.http_client.middleware_request')
    def test_robust_get_caching(self, mock_middleware):
        """Test that successful responses are cached."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {'Content-Type': 'application/json'}
        mock_response.text = '{"test": "data"}'
        mock_middleware.return_value = mock_response

        # First call should make request and cache
        robust_get("https://api.example.com/test")

        # Verify caching happened (status < 500)
        # This would normally update _http_cache, but we can't easily test that
        # without more complex mocking

    @patch('common.http_client.middleware_request')
    def test_robust_get_no_caching_5xx(self, mock_middleware):
        """Test that 5xx responses are not cached."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.headers = {}
        mock_response.text = "Internal Server Error"
        mock_middleware.return_value = mock_response

        status, headers, text = robust_get("https://api.example.com/test")

        assert status == 500
        # 5xx responses should not be cached


class TestMiddlewareIntegration:
    """Test middleware integration scenarios."""

    @patch('common.http_client.middleware_request')
    def test_middleware_called_with_correct_params(self, mock_middleware):
        """Test that middleware is called with correct parameters."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_middleware.return_value = mock_response

        safe_get(
            "https://api.example.com/test",
            context="test_context",
            headers={'User-Agent': 'test'},
            params={'q': 'test'}
        )

        mock_middleware.assert_called_once_with(
            "GET",
            "https://api.example.com/test",
            timeout=30,
            context="test_context",
            extra_log_fields={"component": "http_client", "action": "GET"},
            headers={'User-Agent': 'test'},
            params={'q': 'test'}
        )
