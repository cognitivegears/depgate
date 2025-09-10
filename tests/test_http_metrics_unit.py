"""Unit tests for HTTP metrics tracking."""

import pytest

from common.http_metrics import HttpMetrics, increment, add_wait, snapshot


class TestHttpMetrics:
    """Test HttpMetrics class functionality."""

    def test_increment_counter(self):
        """Test incrementing counters for services."""
        metrics = HttpMetrics()

        # Test initial state
        assert metrics._counters['api.github.com']['attempts_total'] == 0

        # Increment counter
        metrics.increment('api.github.com', 'attempts_total', 1)
        assert metrics._counters['api.github.com']['attempts_total'] == 1

        # Increment by more than 1
        metrics.increment('api.github.com', 'attempts_total', 3)
        assert metrics._counters['api.github.com']['attempts_total'] == 4

        # Test different service
        metrics.increment('gitlab.com', 'retries_total', 2)
        assert metrics._counters['gitlab.com']['retries_total'] == 2
        assert metrics._counters['api.github.com']['retries_total'] == 0  # Should not affect other counters

    def test_add_wait_time(self):
        """Test adding wait time for services."""
        metrics = HttpMetrics()

        # Test initial state
        assert metrics._wait_times['api.github.com'] == 0.0

        # Add wait time
        metrics.add_wait('api.github.com', 1.5)
        assert metrics._wait_times['api.github.com'] == 1.5

        # Add more wait time
        metrics.add_wait('api.github.com', 2.5)
        assert metrics._wait_times['api.github.com'] == 4.0

        # Test different service
        metrics.add_wait('gitlab.com', 3.0)
        assert metrics._wait_times['gitlab.com'] == 3.0
        assert metrics._wait_times['api.github.com'] == 4.0

    def test_snapshot(self):
        """Test generating metrics snapshot."""
        metrics = HttpMetrics()

        # Add some data
        metrics.increment('api.github.com', 'attempts_total', 5)
        metrics.increment('api.github.com', 'retries_total', 2)
        metrics.increment('api.github.com', 'rate_limit_hits_total', 1)
        metrics.add_wait('api.github.com', 10.5)

        metrics.increment('gitlab.com', 'attempts_total', 3)
        metrics.add_wait('gitlab.com', 5.0)

        snapshot_data = metrics.snapshot()

        # Check structure
        assert 'api.github.com' in snapshot_data
        assert 'gitlab.com' in snapshot_data

        # Check GitHub metrics
        github_metrics = snapshot_data['api.github.com']
        assert github_metrics['counters']['attempts_total'] == 5
        assert github_metrics['counters']['retries_total'] == 2
        assert github_metrics['counters']['rate_limit_hits_total'] == 1
        assert github_metrics['wait_time_total_sec'] == 10.5

        # Check GitLab metrics
        gitlab_metrics = snapshot_data['gitlab.com']
        assert gitlab_metrics['counters']['attempts_total'] == 3
        assert gitlab_metrics['wait_time_total_sec'] == 5.0

    def test_snapshot_empty_metrics(self):
        """Test snapshot with no metrics recorded."""
        metrics = HttpMetrics()
        snapshot_data = metrics.snapshot()

        assert snapshot_data == {}

    def test_reset(self):
        """Test resetting all metrics."""
        metrics = HttpMetrics()

        # Add some data
        metrics.increment('api.github.com', 'attempts_total', 5)
        metrics.add_wait('api.github.com', 10.5)

        # Verify data exists
        assert metrics._counters['api.github.com']['attempts_total'] == 5
        assert metrics._wait_times['api.github.com'] == 10.5

        # Reset
        metrics.reset()

        # Verify data is cleared
        assert metrics._counters['api.github.com']['attempts_total'] == 0
        assert metrics._wait_times['api.github.com'] == 0.0

    def test_thread_safety(self):
        """Test that metrics operations are thread-safe."""
        metrics = HttpMetrics()

        # This is a basic test - in a real scenario we'd use threading
        # to test concurrent access, but for unit tests this verifies
        # that the locking mechanism doesn't break basic functionality

        metrics.increment('api.github.com', 'attempts_total', 1)
        metrics.add_wait('api.github.com', 1.0)

        assert metrics._counters['api.github.com']['attempts_total'] == 1
        assert metrics._wait_times['api.github.com'] == 1.0


class TestGlobalFunctions:
    """Test global convenience functions."""

    def test_global_increment(self):
        """Test global increment function."""
        # Note: This uses the global _metrics instance
        # In a real test suite, we'd want to mock or reset this

        # Reset global metrics first (if possible)
        from common.http_metrics import _metrics
        _metrics.reset()

        increment('api.github.com', 'attempts_total', 3)
        increment('api.github.com', 'retries_total', 1)

        snapshot_data = snapshot()
        assert snapshot_data['api.github.com']['counters']['attempts_total'] == 3
        assert snapshot_data['api.github.com']['counters']['retries_total'] == 1

    def test_global_add_wait(self):
        """Test global add_wait function."""
        from common.http_metrics import _metrics
        _metrics.reset()

        add_wait('api.github.com', 2.5)
        add_wait('api.github.com', 1.5)

        snapshot_data = snapshot()
        assert snapshot_data['api.github.com']['wait_time_total_sec'] == 4.0

    def test_global_snapshot(self):
        """Test global snapshot function."""
        from common.http_metrics import _metrics
        _metrics.reset()

        increment('api.github.com', 'attempts_total', 1)
        add_wait('api.github.com', 1.0)

        snapshot_data = snapshot()
        assert 'api.github.com' in snapshot_data
        assert snapshot_data['api.github.com']['counters']['attempts_total'] == 1
        assert snapshot_data['api.github.com']['wait_time_total_sec'] == 1.0
