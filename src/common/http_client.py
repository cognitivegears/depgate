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


def safe_get(url: str, *, context: str, **kwargs: Any) -> requests.Response:
    """Perform a GET request with consistent error handling.

    Args:
        url: Target URL.
        context: Human-readable source tag for logs (e.g., "npm", "pypi", "maven").
        **kwargs: Passed through to requests.get.

    Returns:
        requests.Response: The HTTP response object.
    """
    try:
        return requests.get(url, timeout=Constants.REQUEST_TIMEOUT, **kwargs)
    except requests.Timeout:
        logging.error(
            "%s request timed out after %s seconds",
            context,
            Constants.REQUEST_TIMEOUT,
        )
        sys.exit(ExitCodes.CONNECTION_ERROR.value)
    except requests.RequestException as exc:  # includes ConnectionError
        logging.error("%s connection error: %s", context, exc)
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
    """Perform GET request with timeout, retries, and caching.

    Args:
        url: Target URL
        headers: Optional request headers
        **kwargs: Additional requests.get parameters

    Returns:
        Tuple of (status_code, headers_dict, text_content)
    """
    cache_key = _get_cache_key('GET', url, headers)

    # Check cache first
    if cache_key in _http_cache and _is_cache_valid(_http_cache[cache_key]):
        cached_data, _ = _http_cache[cache_key]
        return cached_data

    last_exception = None

    for attempt in range(Constants.HTTP_RETRY_MAX):
        try:
            delay = Constants.HTTP_RETRY_BASE_DELAY_SEC * (2 ** attempt)
            if attempt > 0:
                time.sleep(delay)

            response = requests.get(
                url,
                timeout=Constants.REQUEST_TIMEOUT,
                headers=headers,
                **kwargs
            )

            # Cache successful responses
            if response.status_code < 500:  # Don't cache server errors
                cache_data = (response.status_code, dict(response.headers), response.text)
                _http_cache[cache_key] = (cache_data, time.time())

            return response.status_code, dict(response.headers), response.text

        except requests.Timeout:
            last_exception = "timeout"
            continue
        except requests.RequestException as exc:
            last_exception = str(exc)
            continue

    # All retries failed
    return 0, {}, f"Request failed after {Constants.HTTP_RETRY_MAX} attempts: {last_exception}"


def get_json(
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    **kwargs: Any
) -> Tuple[int, Dict[str, str], Optional[Any]]:
    """Perform GET request and parse JSON response.

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
            return status_code, response_headers, json.loads(text)
        except json.JSONDecodeError:
            return status_code, response_headers, None

    return status_code, response_headers, None


def safe_post(
    url: str,
    *,
    context: str,
    data: Optional[str] = None,
    **kwargs: Any,
) -> requests.Response:
    """Perform a POST request with consistent error handling.

    Args:
        url: Target URL.
        context: Human-readable source tag for logs (e.g., "npm").
        data: Optional payload for the POST body.
        **kwargs: Passed through to requests.post.

    Returns:
        requests.Response: The HTTP response object.
    """
    try:
        return requests.post(url, data=data, timeout=Constants.REQUEST_TIMEOUT, **kwargs)
    except requests.Timeout:
        logging.error(
            "%s request timed out after %s seconds",
            context,
            Constants.REQUEST_TIMEOUT,
        )
        sys.exit(ExitCodes.CONNECTION_ERROR.value)
    except requests.RequestException as exc:  # includes ConnectionError
        logging.error("%s connection error: %s", context, exc)
        sys.exit(ExitCodes.CONNECTION_ERROR.value)
