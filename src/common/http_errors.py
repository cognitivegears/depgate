"""Custom exceptions for HTTP rate limiting and retry operations."""

from typing import Optional, Dict, Any


class RateLimitExhausted(Exception):
    """Raised when rate limit is exhausted and no more retries are possible.

    Attributes:
        service: The hostname of the service that triggered the rate limit.
        method: HTTP method used in the request.
        url: The URL that was requested.
        attempts: Number of attempts made before exhaustion.
        reason: Human-readable reason for exhaustion.
        headers: Response headers from the last attempt.
        last_status: HTTP status code from the last attempt.
    """

    def __init__(
        self,
        service: str,
        method: str,
        url: str,
        attempts: int,
        reason: str,
        headers: Optional[Dict[str, str]] = None,
        last_status: Optional[int] = None
    ):
        self.service = service
        self.method = method
        self.url = url
        self.attempts = attempts
        self.reason = reason
        self.headers = headers or {}
        self.last_status = last_status

        message = (
            f"Rate limit exhausted for {service} after {attempts} attempts: {reason}. "
            f"Last status: {last_status}"
        )
        super().__init__(message)


class RetryBudgetExceeded(Exception):
    """Raised when computed wait time exceeds remaining retry budget/time cap.

    Attributes:
        service: The hostname of the service.
        method: HTTP method used in the request.
        url: The URL that was requested.
        attempt: Current attempt number.
        computed_wait: The computed wait time in seconds.
        remaining_budget: Remaining time budget in seconds.
        reason: Human-readable reason for exceeding budget.
    """

    def __init__(
        self,
        service: str,
        method: str,
        url: str,
        attempt: int,
        computed_wait: float,
        remaining_budget: float,
        reason: str
    ):
        self.service = service
        self.method = method
        self.url = url
        self.attempt = attempt
        self.computed_wait = computed_wait
        self.remaining_budget = remaining_budget
        self.reason = reason

        message = (
            f"Retry budget exceeded for {service} on attempt {attempt}: "
            f"computed wait {computed_wait:.2f}s exceeds remaining budget {remaining_budget:.2f}s. "
            f"Reason: {reason}"
        )
        super().__init__(message)
