"""Shared HTTP helpers for registry clients.

Encapsulates common request/timeout error handling so individual
registry modules avoid duplicating try/except blocks.
"""
from __future__ import annotations

import logging
import sys
from typing import Any, Optional

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
