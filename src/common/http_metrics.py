"""In-process HTTP metrics registry for rate limiting and retry tracking."""

import threading
from typing import Dict, Any
from collections import defaultdict


class HttpMetrics:
    """Thread-safe in-process metrics registry for HTTP operations.

    Tracks per-service counters and timing data for rate limiting and retry operations.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._counters: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._wait_times: Dict[str, float] = defaultdict(float)

    def increment(self, service: str, metric: str, n: int = 1) -> None:
        """Increment a counter for the given service and metric.

        Args:
            service: Service hostname (e.g., 'api.github.com')
            metric: Metric name (e.g., 'attempts_total', 'retries_total')
            n: Amount to increment (default: 1)
        """
        with self._lock:
            self._counters[service][metric] += n

    def add_wait(self, service: str, seconds: float) -> None:
        """Add wait time for the given service.

        Args:
            service: Service hostname
            seconds: Wait time in seconds to add
        """
        with self._lock:
            self._wait_times[service] += seconds

    def snapshot(self) -> Dict[str, Any]:
        """Return a snapshot of all current metrics.

        Returns:
            Dict containing per-service metrics with counters and total wait times
        """
        with self._lock:
            result = {}
            for service in set(self._counters.keys()) | set(self._wait_times.keys()):
                result[service] = {
                    'counters': dict(self._counters[service]),
                    'wait_time_total_sec': self._wait_times[service]
                }
            return result

    def reset(self) -> None:
        """Reset all metrics (primarily for testing)."""
        with self._lock:
            self._counters.clear()
            self._wait_times.clear()


# Global metrics instance
_metrics = HttpMetrics()


def increment(service: str, metric: str, n: int = 1) -> None:
    """Increment a counter for the given service and metric.

    Args:
        service: Service hostname
        metric: Metric name
        n: Amount to increment
    """
    _metrics.increment(service, metric, n)


def add_wait(service: str, seconds: float) -> None:
    """Add wait time for the given service.

    Args:
        service: Service hostname
        seconds: Wait time in seconds
    """
    _metrics.add_wait(service, seconds)


def snapshot() -> Dict[str, Any]:
    """Return a snapshot of all current metrics.

    Returns:
        Dict containing per-service metrics
    """
    return _metrics.snapshot()
