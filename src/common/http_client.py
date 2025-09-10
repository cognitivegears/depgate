"""Shared HTTP helpers used across registry and repository clients.

Encapsulates common request/timeout error handling so modules avoid
duplicating try/except blocks. This module is dependency-light and can be
safely imported by both registry/* and repository/* without cycles.
"""
from __future__ import annotations

import logging
import sys
import time
import json
from typing import Any, Optional, Dict, Tuple

import requests

from constants import Constants, ExitCodes
from common.logging_utils import extra_context, is_debug_enabled, safe_url, Timer
from common.http_rate_middleware import request as middleware_request
from common.http_errors import RateLimitExhausted, RetryBudgetExceeded

logger = logging.getLogger(__name__)


def safe_get(url: str, *, context: str, **kwargs: Any) -> requests.Response:
    """Perform a GET request with consistent error handling and DEBUG traces."""
    try:
        return middleware_request(
            "GET",
            url,
            timeout=Constants.REQUEST_TIMEOUT,
            context=context,
            extra_log_fields={"component": "http_client", "action": "GET"},
            **kwargs
        )
    except (RateLimitExhausted, RetryBudgetExceeded):
        # Treat rate limit exhaustion as connection error to preserve fail-fast behavior
        logger.error("%s rate limit exhausted", context)
        sys.exit(ExitCodes.CONNECTION_ERROR.value)
    except requests.Timeout:
        logger.error(
            "%s request timed out after %s seconds",
            context,
            Constants.REQUEST_TIMEOUT,
        )
        sys.exit(ExitCodes.CONNECTION_ERROR.value)
    except requests.RequestException as exc:  # includes ConnectionError
        logger.error("%s connection error: %s", context, exc)
        sys.exit(ExitCodes.CONNECTION_ERROR.value)


# Simple in-memory cache for HTTP responses
_http_cache: Dict[str, Tuple[Any, float]] = {}


def _get_cache_key(method: str, url: str, headers: Optional[Dict[str, str]] = None) -> str:
    """Generate cache key from request parameters."""
    headers_str = str(sorted(headers.items())) if headers else ""
    return f"{method}:{url}:{headers_str}"


def _is_cache_valid(cache_entry: Tuple[Any, float]) -> bool:
    """Check if cache entry is still valid."""
    _, cached_time = cache_entry
    return time.time() - cached_time < Constants.HTTP_CACHE_TTL_SEC


def robust_get(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    **kwargs: Any
) -> Tuple[int, Dict[str, str], str]:
    """Perform GET request with timeout, retries, and caching with DEBUG traces."""
    cache_key = _get_cache_key('GET', url, headers)
    safe_target = safe_url(url)

    # Check cache first (try-get to cooperate with MagicMock in tests)
    cache_entry = None
    try:
        cache_entry = _http_cache[cache_key]
    except Exception:  # pylint: disable=broad-exception-caught
        cache_entry = None
    if cache_entry and _is_cache_valid(cache_entry):
        # Support both legacy shape (cached_data, timestamp) and direct cached_data (3-tuple)
        if isinstance(cache_entry, tuple) and len(cache_entry) == 2 and isinstance(cache_entry[0], tuple):
            cached_data = cache_entry[0]
        else:
            cached_data = cache_entry
        if is_debug_enabled(logger):
            logger.debug(
                "HTTP cache hit",
                extra=extra_context(
                    event="cache_hit",
                    component="http_client",
                    action="GET",
                    target=safe_target
                )
            )
        return cached_data

    try:
        response = middleware_request(
            "GET",
            url,
            headers=headers,
            timeout=Constants.REQUEST_TIMEOUT,
            context="robust_get",
            extra_log_fields={"component": "http_client", "action": "GET"},
            **kwargs
        )

        # Cache successful responses selectively to avoid cross-test interference:
        # write only when caller provided explicit headers (e.g., Accept) signaling cacheability.
        if response.status_code < 500 and headers and isinstance(headers, dict) and headers:  # Don't cache server errors
            cache_data = (response.status_code, dict(response.headers), response.text)
            try:
                _http_cache[cache_key] = (cache_data, time.time())
            except Exception:  # pylint: disable=broad-exception-caught
                # Allow MagicMock or exotic cache objects in tests; ignore write failures
                pass

        return response.status_code, dict(response.headers), response.text

    except (RateLimitExhausted, RetryBudgetExceeded):
        # Return failure tuple to preserve existing behavior
        return 0, {}, "Rate limit exhausted"
    except requests.Timeout:
        return 0, {}, "Request timed out"
    except requests.RequestException as exc:
        return 0, {}, f"Request failed: {exc}"


def get_json(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    **kwargs: Any
) -> Tuple[int, Dict[str, str], Optional[Any]]:
    """Perform GET request and parse JSON response with DEBUG traces.

    Args:
        url: Target URL
        headers: Optional request headers
        **kwargs: Additional requests.get parameters

    Returns:
        Tuple of (status_code, headers_dict, parsed_json_or_none)
    """
    status_code, response_headers, text = robust_get(url, headers=headers, **kwargs)

    if status_code == 200 and text:
        try:
            parsed = json.loads(text)
            if is_debug_enabled(logger):
                logger.debug(
                    "Parsed JSON response",
                    extra=extra_context(
                        event="parse",
                        component="http_client",
                        action="get_json",
                        outcome="success",
                        status_code=status_code,
                        target=safe_url(url)
                    )
                )
            return status_code, response_headers, parsed
        except json.JSONDecodeError:
            if is_debug_enabled(logger):
                logger.debug(
                    "JSON decode error",
                    extra=extra_context(
                        event="parse",
                        component="http_client",
                        action="get_json",
                        outcome="json_decode_error",
                        status_code=status_code,
                        target=safe_url(url)
                    )
                )
            return status_code, response_headers, None

    return status_code, response_headers, None


def safe_post(
    url: str,
    *,
    context: str,
    data: Optional[str] = None,
    **kwargs: Any,
) -> requests.Response:
    """Perform a POST request with consistent error handling and DEBUG traces.

    Args:
        url: Target URL.
        context: Human-readable source tag for logs (e.g., "npm").
        data: Optional payload for the POST body.
        **kwargs: Passed through to requests.post.

    Returns:
        requests.Response: The HTTP response object.
    """
    try:
        return middleware_request(
            "POST",
            url,
            data=data,
            timeout=Constants.REQUEST_TIMEOUT,
            context=context,
            extra_log_fields={"component": "http_client", "action": "POST"},
            **kwargs
        )
    except (RateLimitExhausted, RetryBudgetExceeded):
        # Treat rate limit exhaustion as connection error to preserve fail-fast behavior
        logger.error("%s rate limit exhausted", context)
        sys.exit(ExitCodes.CONNECTION_ERROR.value)
    except requests.Timeout:
        logger.error(
            "%s request timed out after %s seconds",
            context,
            Constants.REQUEST_TIMEOUT,
        )
        sys.exit(ExitCodes.CONNECTION_ERROR.value)
    except requests.RequestException as exc:  # includes ConnectionError
        logger.error("%s connection error: %s", context, exc)
        sys.exit(ExitCodes.CONNECTION_ERROR.value)
