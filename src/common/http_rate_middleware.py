"""HTTP rate limiting and retry middleware."""

from __future__ import annotations

import logging
import random
import threading
import time
from email.utils import parsedate_to_datetime
from typing import Dict, Optional, Any
from urllib.parse import urlparse

import requests

from common.http_errors import RateLimitExhausted, RetryBudgetExceeded
from common.http_metrics import increment, add_wait
from common.http_policy import HttpRetryPolicy, HttpBackoffStrategy, load_http_policy_from_constants, is_idempotent
from common.logging_utils import extra_context, is_debug_enabled, safe_url
from constants import Constants

logger = logging.getLogger(__name__)

# Helper sanitization for PyPI URL name segments
def _sanitize_pypi_name_segment(name: str) -> str:
    """Strip version specifiers/extras/markers from a PyPI package name segment."""
    s = str(name).strip()
    # Cut at first occurrence of any comparator/extras/marker tokens
    cutpoints = []
    for token in ("===", ">=", "<=", "==", "~=", "!=", ">", "<", "[", ";", " "):
        idx = s.find(token)
        if idx != -1:
            cutpoints.append(idx)
    if cutpoints:
        s = s[: min(cutpoints)]
    return s

def _sanitize_pypi_url(url: str) -> str:
    """If URL targets PyPI JSON API, ensure the name segment excludes version specifiers."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if "pypi.org" not in host:
            return url
        parts = parsed.path.split("/")
        # find 'pypi' segment
        try:
            i = parts.index("pypi")
        except ValueError:
            return url
        if len(parts) > i + 1 and parts[i + 1]:
            name_seg = parts[i + 1]
            sanitized = _sanitize_pypi_name_segment(name_seg)
            if sanitized != name_seg:
                parts[i + 1] = sanitized
                new_path = "/".join(parts)
                return parsed._replace(path=new_path).geturl()
        return url
    except Exception:
        return url

# Per-service cooldown tracking
_service_cooldowns: Dict[str, float] = {}
_cooldown_lock = threading.Lock()


def get_hostname(url: str) -> str:
    """Extract hostname from URL.

    Args:
        url: The URL to parse

    Returns:
        Hostname string
    """
    return urlparse(url).hostname or ""


def parse_retry_after(headers: Dict[str, str], now: float) -> Optional[float]:
    """Parse Retry-After header value.

    Args:
        headers: Response headers
        now: Current timestamp

    Returns:
        Seconds to wait, or None if not present/parsable
    """
    retry_after = headers.get('Retry-After')
    if not retry_after:
        return None

    try:
        # Try parsing as integer seconds
        return float(retry_after)
    except ValueError:
        pass

    try:
        # Try parsing as HTTP-date
        dt = parsedate_to_datetime(retry_after)
        return (dt.timestamp() - now)
    except (ValueError, TypeError):
        pass

    return None


def parse_rate_reset(headers: Dict[str, str], service: str) -> Optional[float]:
    """Parse rate limit reset timestamp from service-specific headers.

    Args:
        headers: Response headers
        service: Service hostname

    Returns:
        Reset timestamp, or None if not present/parsable
    """
    if service in ('api.github.com', 'github.com'):
        remaining = headers.get('X-RateLimit-Remaining')
        reset_ts = headers.get('X-RateLimit-Reset')
        if remaining and reset_ts and remaining.isdigit() and int(remaining) <= 0:
            try:
                return float(reset_ts)
            except ValueError:
                pass
    elif service == 'gitlab.com':
        remaining = headers.get('RateLimit-Remaining')
        reset_ts = headers.get('RateLimit-Reset')
        if remaining and reset_ts and remaining.isdigit() and int(remaining) <= 0:
            try:
                # GitLab can return seconds-until or epoch timestamp
                reset_val = float(reset_ts)
                if reset_val < 1e10:  # Likely seconds-until
                    return time.time() + reset_val
                else:  # Epoch timestamp
                    return reset_val
            except ValueError:
                pass

    return None


def compute_wait(
    policy: HttpRetryPolicy,
    attempt: int,
    headers: Dict[str, str],
    now: float,
    service: str
) -> float:
    """Compute wait time for current attempt.

    Args:
        policy: Retry policy
        attempt: Current attempt number (1-based)
        headers: Response headers
        now: Current timestamp
        service: Service hostname

    Returns:
        Seconds to wait
    """
    # Priority 1: Retry-After header
    if policy.respect_retry_after:
        retry_after = parse_retry_after(headers, now)
        if retry_after is not None:
            return min(retry_after, policy.max_backoff)

    # Priority 2: Service-specific rate limit headers
    if policy.respect_reset_headers:
        reset_ts = parse_rate_reset(headers, service)
        if reset_ts is not None:
            wait = max(0, reset_ts - now)
            return min(wait, policy.max_backoff)

    # Priority 3: Backoff strategy
    if attempt == 1:
        backoff = policy.initial_backoff
    else:
        if policy.strategy == HttpBackoffStrategy.FIXED:
            backoff = policy.initial_backoff
        elif policy.strategy == HttpBackoffStrategy.EXPONENTIAL:
            backoff = policy.initial_backoff * (policy.multiplier ** (attempt - 1))
        elif policy.strategy == HttpBackoffStrategy.EXPONENTIAL_JITTER:
            backoff = policy.initial_backoff * (policy.multiplier ** (attempt - 1))
            jitter = backoff * policy.jitter_pct
            backoff += random.uniform(-jitter, jitter)
        else:
            backoff = policy.initial_backoff

    return max(0, min(backoff, policy.max_backoff))


def _get_service_cooldown(service: str) -> float:
    """Get current cooldown for service."""
    with _cooldown_lock:
        return _service_cooldowns.get(service, 0)


def _set_service_cooldown(service: str, cooldown_until: float) -> None:
    """Set cooldown for service until specified time."""
    with _cooldown_lock:
        _service_cooldowns[service] = cooldown_until


def _clear_service_cooldown(service: str) -> None:
    """Clear cooldown for service."""
    with _cooldown_lock:
        _service_cooldowns.pop(service, None)


def request(
    method: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    data: Optional[str] = None,
    json: Optional[Any] = None,
    timeout: Optional[float] = None,
    allow_retry_non_idempotent: Optional[bool] = None,
    context: Optional[str] = None,
    session: Optional[requests.Session] = None,
    extra_log_fields: Optional[Dict[str, Any]] = None
) -> requests.Response:
    """Make HTTP request with rate limiting and retry logic.

    Args:
        method: HTTP method
        url: Target URL
        headers: Request headers
        params: Query parameters
        data: Request body data
        json: JSON request body
        timeout: Request timeout
        allow_retry_non_idempotent: Override policy for non-idempotent retries
        context: Logging context
        session: Requests session to use
        extra_log_fields: Additional logging fields

    Returns:
        requests.Response object

    Raises:
        RateLimitExhausted: When rate limit is exhausted
        RetryBudgetExceeded: When retry budget is exceeded
    """
    # Sanitize known problematic URL patterns (e.g., PyPI /pypi/{name}/json with specifiers)
    orig_url = url
    try:
        url = _sanitize_pypi_url(url)
    except Exception:
        # Defensive: never fail request due to sanitization
        pass

    # Load policies
    default_policy, per_service_overrides = load_http_policy_from_constants()

    # Determine service and policy
    hostname = get_hostname(url)
    policy = per_service_overrides.get(hostname, default_policy)

    # Override non-idempotent retry if specified
    if allow_retry_non_idempotent is not None:
        policy = HttpRetryPolicy(**policy.__dict__)
        policy.allow_non_idempotent_retry = allow_retry_non_idempotent

    safe_target = safe_url(url)
    timeout = timeout or Constants.REQUEST_TIMEOUT
    headers = headers or {}
    extra_log_fields = extra_log_fields or {}

    # Check if method allows retries
    can_retry = is_idempotent(method) or policy.allow_non_idempotent_retry

    start_time = time.time()
    attempt = 0
    total_wait_time = 0.0

    while True:
        attempt += 1

        # Check service cooldown
        cooldown_until = _get_service_cooldown(hostname)
        now = time.time()
        if now < cooldown_until:
            wait_needed = cooldown_until - now
            if total_wait_time + wait_needed > policy.total_retry_time_cap_sec:
                raise RetryBudgetExceeded(
                    hostname, method, url, attempt, wait_needed,
                    policy.total_retry_time_cap_sec - total_wait_time,
                    "service cooldown would exceed total retry time cap"
                )
            if wait_needed > timeout:
                raise RetryBudgetExceeded(
                    hostname, method, url, attempt, wait_needed, timeout,
                    "service cooldown exceeds request timeout"
                )

            if is_debug_enabled(logger):
                logger.debug(
                    "Service cooldown active",
                    extra=extra_context(
                        event="cooldown_wait",
                        service=hostname,
                        method=method,
                        target=safe_target,
                        attempt=attempt,
                        wait_sec=wait_needed,
                        **extra_log_fields
                    )
                )

            time.sleep(wait_needed)
            total_wait_time += wait_needed
            add_wait(hostname, wait_needed)

        # Make request
        try:
            if is_debug_enabled(logger):
                logger.debug(
                    "HTTP request attempt",
                    extra=extra_context(
                        event="http_request_attempt",
                        service=hostname,
                        method=method,
                        target=safe_target,
                        attempt=attempt,
                        can_retry=can_retry,
                        **extra_log_fields
                    )
                )

            requester = session or requests
            response = requester.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                data=data,
                json=json,
                timeout=timeout
            )

            increment(hostname, 'attempts_total')

            # Success or non-retryable error
            if response.status_code not in (429, 403) or not can_retry or attempt > policy.max_retries:
                if response.status_code in (429, 403):
                    increment(hostname, 'rate_limit_hits_total')
                    if attempt > policy.max_retries:
                        raise RateLimitExhausted(
                            hostname, method, url, attempt,
                            f"max retries ({policy.max_retries}) exceeded",
                            dict(response.headers), response.status_code
                        )

                if is_debug_enabled(logger):
                    logger.debug(
                        "HTTP response",
                        extra=extra_context(
                            event="http_response",
                            service=hostname,
                            method=method,
                            target=safe_target,
                            attempt=attempt,
                            status_code=response.status_code,
                            outcome="success",
                            **extra_log_fields
                        )
                    )
                return response

            # Rate limited - compute wait
            wait_time = compute_wait(policy, attempt, dict(response.headers), time.time(), hostname)

            if total_wait_time + wait_time > policy.total_retry_time_cap_sec:
                raise RetryBudgetExceeded(
                    hostname, method, url, attempt, wait_time,
                    policy.total_retry_time_cap_sec - total_wait_time,
                    "computed wait would exceed total retry time cap"
                )

            if wait_time > timeout:
                raise RetryBudgetExceeded(
                    hostname, method, url, attempt, wait_time, timeout,
                    "computed wait exceeds request timeout"
                )

            # Set service cooldown
            _set_service_cooldown(hostname, time.time() + wait_time)

            if is_debug_enabled(logger):
                logger.debug(
                    "Rate limited, will retry",
                    extra=extra_context(
                        event="rate_limited_retry",
                        service=hostname,
                        method=method,
                        target=safe_target,
                        attempt=attempt,
                        status_code=response.status_code,
                        wait_sec=wait_time,
                        total_wait_sec=total_wait_time + wait_time,
                        **extra_log_fields
                    )
                )

            time.sleep(wait_time)
            total_wait_time += wait_time
            add_wait(hostname, wait_time)
            increment(hostname, 'retries_total')

        except requests.Timeout:
            if not can_retry or attempt > policy.max_retries:
                raise
            increment(hostname, 'attempts_total')
            # For timeouts, use backoff without headers
            wait_time = compute_wait(policy, attempt, {}, time.time(), hostname)
            if total_wait_time + wait_time > policy.total_retry_time_cap_sec:
                raise RetryBudgetExceeded(
                    hostname, method, url, attempt, wait_time,
                    policy.total_retry_time_cap_sec - total_wait_time,
                    "timeout backoff would exceed total retry time cap"
                )
            time.sleep(wait_time)
            total_wait_time += wait_time
            add_wait(hostname, wait_time)
            increment(hostname, 'retries_total')

        except requests.RequestException as exc:
            if not can_retry or attempt > policy.max_retries:
                raise
            increment(hostname, 'attempts_total')
            # For other exceptions, use backoff without headers
            wait_time = compute_wait(policy, attempt, {}, time.time(), hostname)
            if total_wait_time + wait_time > policy.total_retry_time_cap_sec:
                raise RetryBudgetExceeded(
                    hostname, method, url, attempt, wait_time,
                    policy.total_retry_time_cap_sec - total_wait_time,
                    f"request exception backoff would exceed total retry time cap: {exc}"
                )
            time.sleep(wait_time)
            total_wait_time += wait_time
            add_wait(hostname, wait_time)
            increment(hostname, 'retries_total')
