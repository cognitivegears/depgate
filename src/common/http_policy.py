"""HTTP retry and rate limit policy configuration."""

from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Dict, Optional

from constants import Constants


class HttpBackoffStrategy(enum.Enum):
    """Backoff strategies for retry delays."""
    FIXED = "fixed"
    EXPONENTIAL = "exponential"
    EXPONENTIAL_JITTER = "exponential_jitter"


@dataclass
class HttpRetryPolicy:
    """Configuration for HTTP retry behavior.

    Attributes:
        max_retries: Maximum number of retry attempts (0 = no retries)
        initial_backoff: Initial backoff delay in seconds
        multiplier: Backoff multiplier for exponential strategies
        jitter_pct: Jitter percentage (0.0-1.0) for jitter strategies
        max_backoff: Maximum backoff delay in seconds
        total_retry_time_cap_sec: Total time cap for all retries combined
        strategy: Backoff strategy to use
        respect_retry_after: Whether to respect Retry-After headers
        respect_reset_headers: Whether to respect rate limit reset headers
        allow_non_idempotent_retry: Whether to allow retries for non-idempotent methods
    """
    max_retries: int
    initial_backoff: float
    multiplier: float
    jitter_pct: float
    max_backoff: float
    total_retry_time_cap_sec: float
    strategy: HttpBackoffStrategy
    respect_retry_after: bool
    respect_reset_headers: bool
    allow_non_idempotent_retry: bool


def load_http_policy_from_constants() -> tuple[HttpRetryPolicy, Dict[str, HttpRetryPolicy]]:
    """Load HTTP retry policy from Constants.

    Returns:
        Tuple of (default_policy, per_service_overrides_by_host)
    """
    # Default policy - fail-fast to preserve existing behavior
    default_policy = HttpRetryPolicy(
        max_retries=getattr(Constants, 'HTTP_RATE_POLICY_DEFAULT_MAX_RETRIES', 0),
        initial_backoff=getattr(Constants, 'HTTP_RATE_POLICY_DEFAULT_INITIAL_BACKOFF_SEC', 0.5),
        multiplier=getattr(Constants, 'HTTP_RATE_POLICY_DEFAULT_MULTIPLIER', 2.0),
        jitter_pct=getattr(Constants, 'HTTP_RATE_POLICY_DEFAULT_JITTER_PCT', 0.2),
        max_backoff=getattr(Constants, 'HTTP_RATE_POLICY_DEFAULT_MAX_BACKOFF_SEC', 60.0),
        total_retry_time_cap_sec=getattr(Constants, 'HTTP_RATE_POLICY_DEFAULT_TOTAL_RETRY_TIME_CAP_SEC', 120.0),
        strategy=HttpBackoffStrategy(getattr(Constants, 'HTTP_RATE_POLICY_DEFAULT_STRATEGY', 'exponential_jitter')),
        respect_retry_after=getattr(Constants, 'HTTP_RATE_POLICY_DEFAULT_RESPECT_RETRY_AFTER', True),
        respect_reset_headers=getattr(Constants, 'HTTP_RATE_POLICY_DEFAULT_RESPECT_RESET_HEADERS', True),
        allow_non_idempotent_retry=getattr(Constants, 'HTTP_RATE_POLICY_DEFAULT_ALLOW_NON_IDEMPOTENT_RETRY', False)
    )

    # Per-service overrides
    per_service_overrides = {}
    overrides_config = getattr(Constants, 'HTTP_RATE_POLICY_PER_SERVICE', {})

    for host, config in overrides_config.items():
        policy = HttpRetryPolicy(
            max_retries=config.get('max_retries', default_policy.max_retries),
            initial_backoff=config.get('initial_backoff_sec', default_policy.initial_backoff),
            multiplier=config.get('multiplier', default_policy.multiplier),
            jitter_pct=config.get('jitter_pct', default_policy.jitter_pct),
            max_backoff=config.get('max_backoff_sec', default_policy.max_backoff),
            total_retry_time_cap_sec=config.get('total_retry_time_cap_sec', default_policy.total_retry_time_cap_sec),
            strategy=HttpBackoffStrategy(config.get('strategy', default_policy.strategy.value)),
            respect_retry_after=config.get('respect_retry_after', default_policy.respect_retry_after),
            respect_reset_headers=config.get('respect_reset_headers', default_policy.respect_reset_headers),
            allow_non_idempotent_retry=config.get('allow_non_idempotent_retry', default_policy.allow_non_idempotent_retry)
        )
        per_service_overrides[host] = policy

    return default_policy, per_service_overrides


def is_idempotent(method: str) -> bool:
    """Check if an HTTP method is idempotent.

    Args:
        method: HTTP method (e.g., 'GET', 'POST')

    Returns:
        True if the method is idempotent, False otherwise
    """
    # RFC 7231: Idempotent methods are GET, HEAD, PUT, DELETE, OPTIONS, TRACE
    return method.upper() in ('GET', 'HEAD', 'PUT', 'DELETE', 'OPTIONS', 'TRACE')
