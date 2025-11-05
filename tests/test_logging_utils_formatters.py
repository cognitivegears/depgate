"""Tests for logging utilities formatters and context management."""

import json
import logging
import pytest
from unittest.mock import patch

from common.logging_utils import (
    HumanFormatter,
    JsonFormatter,
    correlation_context,
    request_context,
    extra_context,
    Timer,
    start_timer,
    is_debug_enabled,
    configure_logging,
    get_correlation_id,
    get_request_id,
    set_correlation_id,
    set_request_id,
    new_correlation_id,
    new_request_id,
)


class TestCorrelationContext:
    """Test correlation ID context management."""

    def test_correlation_context_new_id(self):
        """Test correlation context with new ID."""
        original_id = get_correlation_id()
        with correlation_context() as cid:
            assert cid is not None
            assert len(cid) == 36  # UUID4 length
            assert get_correlation_id() == cid
        assert get_correlation_id() == original_id

    def test_correlation_context_provided_id(self):
        """Test correlation context with provided ID."""
        test_id = "test-correlation-id"
        original_id = get_correlation_id()
        with correlation_context(test_id) as cid:
            assert cid == test_id
            assert get_correlation_id() == test_id
        assert get_correlation_id() == original_id

    def test_nested_correlation_contexts(self):
        """Test nested correlation contexts."""
        with correlation_context("outer") as outer_id:
            assert get_correlation_id() == "outer"
            with correlation_context("inner") as inner_id:
                assert get_correlation_id() == "inner"
            assert get_correlation_id() == "outer"


class TestRequestContext:
    """Test request ID context management."""

    def test_request_context_new_id(self):
        """Test request context with new ID."""
        original_id = get_request_id()
        with request_context() as rid:
            assert rid is not None
            assert len(rid) == 36  # UUID4 length
            assert get_request_id() == rid
        assert get_request_id() == original_id

    def test_request_context_provided_id(self):
        """Test request context with provided ID."""
        test_id = "test-request-id"
        original_id = get_request_id()
        with request_context(test_id) as rid:
            assert rid == test_id
            assert get_request_id() == test_id
        assert get_request_id() == original_id

    def test_nested_request_contexts(self):
        """Test nested request contexts."""
        with request_context("outer") as outer_id:
            assert get_request_id() == "outer"
            with request_context("inner") as inner_id:
                assert get_request_id() == "inner"
            assert get_request_id() == "outer"


class TestExtraContext:
    """Test extra_context function."""

    def test_extra_context_without_ids(self):
        """Test extra_context without correlation/request IDs."""
        context = extra_context(event="test", action="create")
        assert context["event"] == "test"
        assert context["action"] == "create"
        assert "correlation_id" not in context
        assert "request_id" not in context

    def test_extra_context_with_correlation_id(self):
        """Test extra_context with correlation ID."""
        original_id = get_correlation_id()
        set_correlation_id("test-corr-id")
        try:
            context = extra_context(event="test")
            assert context["event"] == "test"
            assert context["correlation_id"] == "test-corr-id"
            assert "request_id" not in context
        finally:
            if original_id:
                set_correlation_id(original_id)

    def test_extra_context_with_request_id(self):
        """Test extra_context with request ID."""
        original_id = get_request_id()
        set_request_id("test-req-id")
        try:
            context = extra_context(action="update")
            assert context["action"] == "update"
            assert context["request_id"] == "test-req-id"
            assert "correlation_id" not in context
        finally:
            if original_id:
                set_request_id(original_id)

    def test_extra_context_with_both_ids(self):
        """Test extra_context with both IDs."""
        original_corr = get_correlation_id()
        original_req = get_request_id()
        set_correlation_id("test-corr-id")
        set_request_id("test-req-id")
        try:
            context = extra_context(event="test")
            assert context["correlation_id"] == "test-corr-id"
            assert context["request_id"] == "test-req-id"
        finally:
            if original_corr:
                set_correlation_id(original_corr)
            if original_req:
                set_request_id(original_req)


class TestTimer:
    """Test Timer class and start_timer function."""

    def test_timer_context_manager(self):
        """Test Timer as context manager."""
        import time
        with Timer() as timer:
            assert timer.start_time is not None
            # Add a small delay to ensure measurable duration on fast systems
            time.sleep(0.001)  # 1ms delay
        assert timer.end_time is not None
        assert timer.duration_ms() > 0

    def test_timer_duration_calculation(self):
        """Test duration calculation."""
        timer = Timer()
        with timer:
            pass
        duration = timer.duration_ms()
        assert isinstance(duration, float)
        assert duration >= 0

    def test_start_timer_function(self):
        """Test start_timer helper function."""
        timer = start_timer()
        assert timer.start_time is not None
        assert timer.end_time is None

    def test_timer_no_end_time(self):
        """Test timer duration when end_time is None."""
        timer = Timer()
        timer.start_time = None
        assert timer.duration_ms() == 0.0


class TestIsDebugEnabled:
    """Test is_debug_enabled function."""

    def test_debug_enabled(self):
        """Test when DEBUG is enabled."""
        logger = logging.getLogger("test_debug_enabled")
        logger.setLevel(logging.DEBUG)
        assert is_debug_enabled(logger)

    def test_debug_disabled(self):
        """Test when DEBUG is disabled."""
        logger = logging.getLogger("test_debug_disabled")
        logger.setLevel(logging.INFO)
        assert not is_debug_enabled(logger)


class TestHumanFormatter:
    """Test HumanFormatter."""

    def test_format_basic_message(self):
        """Test basic message formatting."""
        formatter = HumanFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None
        )
        result = formatter.format(record)
        assert "[INFO] Test message" in result

    def test_format_with_correlation_id(self):
        """Test formatting with correlation ID."""
        formatter = HumanFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None
        )
        record.correlation_id = "test-corr-id"
        result = formatter.format(record)
        assert "[corr:test-corr-id]" in result

    def test_format_with_request_id(self):
        """Test formatting with request ID."""
        formatter = HumanFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None
        )
        record.request_id = "test-req-id"
        result = formatter.format(record)
        assert "[req:test-req-id]" in result

    def test_format_with_extra_fields(self):
        """Test formatting with extra structured fields."""
        formatter = HumanFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None
        )
        record.custom_field = "custom_value"
        record.another_field = 123
        result = formatter.format(record)
        assert "custom_field=custom_value" in result
        assert "another_field=123" in result


class TestJsonFormatter:
    """Test JsonFormatter."""

    def test_format_basic_message(self):
        """Test basic JSON message formatting."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None
        )
        result = formatter.format(record)
        parsed = json.loads(result)
        assert parsed["level"] == "INFO"
        assert parsed["logger"] == "test.logger"
        assert parsed["message"] == "Test message"
        assert "ts" in parsed
        assert "correlation_id" not in parsed
        assert "request_id" not in parsed

    def test_format_with_correlation_id(self):
        """Test JSON formatting with correlation ID."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None
        )
        record.correlation_id = "test-corr-id"
        result = formatter.format(record)
        parsed = json.loads(result)
        assert parsed["correlation_id"] == "test-corr-id"

    def test_format_with_request_id(self):
        """Test JSON formatting with request ID."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None
        )
        record.request_id = "test-req-id"
        result = formatter.format(record)
        parsed = json.loads(result)
        assert parsed["request_id"] == "test-req-id"

    def test_format_with_extra_fields(self):
        """Test JSON formatting with extra structured fields."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None
        )
        record.custom_field = "custom_value"
        record.numeric_field = 42
        result = formatter.format(record)
        parsed = json.loads(result)
        assert parsed["custom_field"] == "custom_value"
        assert parsed["numeric_field"] == 42

    def test_format_omits_none_fields(self):
        """Test that None fields are omitted from JSON."""
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=10,
            msg="Test message",
            args=(),
            exc_info=None
        )
        record.none_field = None
        record.valid_field = "value"
        result = formatter.format(record)
        parsed = json.loads(result)
        assert "none_field" not in parsed
        assert parsed["valid_field"] == "value"


class TestConfigureLogging:
    """Test configure_logging function."""

    @patch.dict('os.environ', {}, clear=True)
    def test_configure_logging_default(self):
        """Test configure_logging with default settings."""
        configure_logging()
        root_logger = logging.getLogger()
        assert root_logger.level == logging.INFO
        stream_handlers = [h for h in root_logger.handlers if isinstance(h, logging.StreamHandler)]
        assert any(isinstance(h.formatter, HumanFormatter) for h in stream_handlers)

    @patch.dict('os.environ', {'DEPGATE_LOG_LEVEL': 'DEBUG'}, clear=True)
    def test_configure_logging_debug_level(self):
        """Test configure_logging with DEBUG level."""
        configure_logging()
        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG

    @patch.dict('os.environ', {'DEPGATE_LOG_FORMAT': 'json'}, clear=True)
    def test_configure_logging_json_format(self):
        """Test configure_logging with JSON format."""
        configure_logging()
        root_logger = logging.getLogger()
        stream_handlers = [h for h in root_logger.handlers if isinstance(h, logging.StreamHandler)]
        assert any(isinstance(h.formatter, JsonFormatter) for h in stream_handlers)

    @patch.dict('os.environ', {'DEPGATE_LOG_LEVEL': 'WARNING', 'DEPGATE_LOG_FORMAT': 'json'}, clear=True)
    def test_configure_logging_combined_settings(self):
        """Test configure_logging with combined settings."""
        configure_logging()
        root_logger = logging.getLogger()
        assert root_logger.level == logging.WARNING
        stream_handlers = [h for h in root_logger.handlers if isinstance(h, logging.StreamHandler)]
        assert any(isinstance(h.formatter, JsonFormatter) for h in stream_handlers)

    def test_configure_logging_no_duplicate_handlers(self):
        """Test that configure_logging doesn't create duplicate handlers."""
        configure_logging()
        root = logging.getLogger()
        stream_handlers = [h for h in root.handlers if isinstance(getattr(h, "formatter", None), (HumanFormatter, JsonFormatter))]
        assert len(stream_handlers) == 1

        # Reconfigure should not add another depgate stream handler
        configure_logging()
        root2 = logging.getLogger()
        stream_handlers2 = [h for h in root2.handlers if isinstance(getattr(h, "formatter", None), (HumanFormatter, JsonFormatter))]
        assert len(stream_handlers2) == 1
