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

logger = logging.getLogger(__name__)


def safe_get(url: str, *, context: str, **kwargs: Any) -> requests.Response:
    """Perform a GET request with consistent error handling and DEBUG traces."""
    safe_target = safe_url(url)
    with Timer() as t:
        if is_debug_enabled(logger):
            logger.debug(
                "HTTP request",
                extra=extra_context(
                    event="http_request",
                    component="http_client",
                    action="GET",
                    target=safe_target,
                    context=context
                )
            )
        try:
            res = requests.get(url, timeout=Constants.REQUEST_TIMEOUT, **kwargs)
            if is_debug_enabled(logger):
                logger.debug(
                    "HTTP response ok",
                    extra=extra_context(
                        event="http_response",
                        component="http_client",
                        action="GET",
                        outcome="success",
                        status_code=res.status_code,
                        duration_ms=t.duration_ms(),
                        target=safe_target,
                        context=context
                    )
                )
            return res
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

    # Check cache first
    if cache_key in _http_cache and _is_cache_valid(_http_cache[cache_key]):
        cached_data, _ = _http_cache[cache_key]
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

    last_exception = None

    for attempt in range(Constants.HTTP_RETRY_MAX):
        with Timer() as t:
            try:
                if is_debug_enabled(logger):
                    logger.debug(
                        "HTTP request",
                        extra=extra_context(
                            event="http_request",
                            component="http_client",
                            action="GET",
                            target=safe_target,
                            attempt=attempt + 1
                        )
                    )

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

                if is_debug_enabled(logger):
                    logger.debug(
                        "HTTP response ok",
                        extra=extra_context(
                            event="http_response",
                            component="http_client",
                            action="GET",
                            outcome="success",
                            status_code=response.status_code,
                            duration_ms=t.duration_ms(),
                            target=safe_target
                        )
                    )
                return response.status_code, dict(response.headers), response.text

            except requests.Timeout:
                last_exception = "timeout"
                if is_debug_enabled(logger):
                    logger.debug(
                        "HTTP timeout",
                        extra=extra_context(
                            event="http_exception",
                            component="http_client",
                            action="GET",
                            outcome="timeout",
                            attempt=attempt + 1,
                            target=safe_target
                        )
                    )
                continue
            except requests.RequestException as exc:
                last_exception = str(exc)
                if is_debug_enabled(logger):
                    logger.debug(
                        "HTTP request exception",
                        extra=extra_context(
                            event="http_exception",
                            component="http_client",
                            action="GET",
                            outcome="request_exception",
                            attempt=attempt + 1,
                            target=safe_target
                        )
                    )
                continue

    # All retries failed
    return 0, {}, f"Request failed after {Constants.HTTP_RETRY_MAX} attempts: {last_exception}"


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
    safe_target = safe_url(url)
    with Timer() as t:
        if is_debug_enabled(logger):
            logger.debug(
                "HTTP request",
                extra=extra_context(
                    event="http_request",
                    component="http_client",
                    action="POST",
                    target=safe_target,
                    context=context
                )
            )
        try:
            res = requests.post(url, data=data, timeout=Constants.REQUEST_TIMEOUT, **kwargs)
            if is_debug_enabled(logger):
                logger.debug(
                    "HTTP response ok",
                    extra=extra_context(
                        event="http_response",
                        component="http_client",
                        action="POST",
                        outcome="success",
                        status_code=res.status_code,
                        duration_ms=t.duration_ms(),
                        target=safe_target,
                        context=context
                    )
                )
            return res
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
