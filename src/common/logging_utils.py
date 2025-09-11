"""Logging utilities for centralized configuration and consistent logging across the application."""

import logging
import contextvars
import uuid
import datetime
import json
import os
import re
import urllib.parse
from typing import Any, Dict, Optional


# Context variables for correlation and request IDs
_correlation_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    '_correlation_id', default=None
)
_request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    '_request_id', default=None
)


def get_correlation_id() -> Optional[str]:
    """Get the current correlation ID from context.

    Returns:
        Optional[str]: The current correlation ID or None if not set.
    """
    return _correlation_id_var.get()


def set_correlation_id(correlation_id: str) -> None:
    """Set the correlation ID in the current context.

    Args:
        correlation_id (str): The correlation ID to set.
    """
    _correlation_id_var.set(correlation_id)


def new_correlation_id() -> str:
    """Generate and set a new correlation ID.

    Returns:
        str: The newly generated correlation ID.
    """
    correlation_id = str(uuid.uuid4())
    set_correlation_id(correlation_id)
    return correlation_id


def get_request_id() -> Optional[str]:
    """Get the current request ID from context.

    Returns:
        Optional[str]: The current request ID or None if not set.
    """
    return _request_id_var.get()


def set_request_id(request_id: str) -> None:
    """Set the request ID in the current context.

    Args:
        request_id (str): The request ID to set.
    """
    _request_id_var.set(request_id)


def new_request_id() -> str:
    """Generate and set a new request ID.

    Returns:
        str: The newly generated request ID.
    """
    request_id = str(uuid.uuid4())
    set_request_id(request_id)
    return request_id


class CorrelationContext:
    """Context manager for setting correlation ID."""

    def __init__(self, correlation_id: Optional[str] = None):
        """Initialize the context manager.

        Args:
            correlation_id (Optional[str]): Correlation ID to use. If None, generates a new one.
        """
        # Generate an ID but do not set the ContextVar yet (set in __enter__)
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.token: Optional[contextvars.Token[Optional[str]]] = None

    def __enter__(self):
        """Enter the context, setting the correlation ID."""
        self.token = _correlation_id_var.set(self.correlation_id)
        return self.correlation_id

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context, resetting the correlation ID."""
        if self.token is not None:
            _correlation_id_var.reset(self.token)


class RequestContext:
    """Context manager for setting request ID."""

    def __init__(self, request_id: Optional[str] = None):
        """Initialize the context manager.

        Args:
            request_id (Optional[str]): Request ID to use. If None, generates a new one.
        """
        # Generate an ID but do not set the ContextVar yet (set in __enter__)
        self.request_id = request_id or str(uuid.uuid4())
        self.token: Optional[contextvars.Token[Optional[str]]] = None

    def __enter__(self):
        """Enter the context, setting the request ID."""
        self.token = _request_id_var.set(self.request_id)
        return self.request_id

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the context, resetting the request ID."""
        if self.token is not None:
            _request_id_var.reset(self.token)

# Backwards compatibility aliases for tests
correlation_context = CorrelationContext
request_context = RequestContext

def extra_context(**kwargs) -> Dict[str, Any]:
    """Merge standard structured fields with provided context.

    Automatically injects request_id if available. Injects correlation_id only
    when an 'event' key is provided in kwargs (milestones/structured events),
    to avoid leaking stale correlation IDs into ad-hoc contexts.

    Args:
        **kwargs: Additional context fields.

    Returns:
        Dict[str, Any]: Merged context dictionary.
    """
    context: Dict[str, Any] = {}

    # Inject request ID if available (always safe/useful)
    request_id = get_request_id()
    if request_id:
        context["request_id"] = request_id

    # Inject correlation ID only for structured events
    if "event" in kwargs:
        correlation_id = get_correlation_id()
        if correlation_id:
            context["correlation_id"] = correlation_id

    # Add provided fields
    context.update(kwargs)

    return context


def redact(text: str) -> str:
    """Redact sensitive information from text.

    Masks Authorization headers and tokens/keys in arbitrary strings.

    Args:
        text (str): The text to redact.

    Returns:
        str: The redacted text.
    """
    if not text:
        return text

    # Redact Authorization headers (case-insensitive)
    text = re.sub(
        r'(?i)\bauthorization\s*:\s*bearer\s+\S+',
        'Authorization: Bearer [REDACTED]',
        text,
    )

    # Redact standalone Bearer tokens (not only in headers)
    text = re.sub(
        r'(?i)\bBearer\s+\S+',
        'Bearer [REDACTED]',
        text,
    )

    # Redact common secret key-value patterns with '='
    secret_keys = r'(token|access_token|key|api_key|apikey|api-key|x-api-key|password|auth|client_secret|private_token)'
    text = re.sub(
        rf'(?i)\b{secret_keys}\b\s*=\s*([^\s&;]+)',
        lambda m: f"{m.group(0).split('=')[0]}=[REDACTED]",
        text,
    )

    # Redact common secret key-value patterns with ':'
    text = re.sub(
        rf'(?i)\b{secret_keys}\b\s*:\s*([^\s&;]+)',
        lambda m: f"{m.group(0).split(':')[0]}: [REDACTED]",
        text,
    )

    return text


def safe_url(url: str) -> str:
    """Return a URL with sensitive query parameters masked.

    Preserves scheme/host/path, masks sensitive query values as '[REDACTED]' without
    percent-encoding the brackets (for readability in human logs).

    Args:
        url (str): The URL to sanitize.

    Returns:
        str: The sanitized URL.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        # Preserve order and case of keys/values
        pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)

        sensitive_params = {
            'token', 'access_token', 'key', 'api_key', 'apikey', 'api-key', 'x-api-key',
            'password', 'auth', 'client_secret', 'private_token'
        }

        masked_pairs = []
        for k, v in pairs:
            if k.lower() in sensitive_params:
                masked_pairs.append((k, '[REDACTED]'))
            else:
                masked_pairs.append((k, v))

        # Reconstruct query string (do not percent-encode '[REDACTED]')
        safe_query = '&'.join(f"{k}={v}" for k, v in masked_pairs)

        safe_url_str = urllib.parse.urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            safe_query,
            parsed.fragment
        ))
        return safe_url_str
    except Exception:  # pylint: disable=broad-exception-caught
        # If parsing fails, return redacted version
        return redact(url)


class Timer:
    """Lightweight timing helper."""

    def __init__(self):
        """Initialize the timer."""
        self.start_time = None
        self.end_time = None

    def start(self):
        """Start the timer (non-context usage) and return self."""
        self.start_time = datetime.datetime.now(datetime.timezone.utc)
        return self

    def __enter__(self):
        """Start the timer for context management."""
        self.start_time = datetime.datetime.now(datetime.timezone.utc)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Stop the timer."""
        self.end_time = datetime.datetime.now(datetime.timezone.utc)

    def duration_ms(self) -> float:
        """Get the duration in milliseconds.

        Returns:
            float: Duration in milliseconds.
        """
        if self.start_time and self.end_time:
            duration = self.end_time - self.start_time
            return duration.total_seconds() * 1000
        return 0.0


def start_timer() -> Timer:
    """Create and start a new timer.

    Returns:
        Timer: A started timer instance.
    """
    return Timer().start()


class HumanFormatter(logging.Formatter):
    """Human-readable log formatter."""

    def format(self, record):
        """Format the log record.

        Args:
            record: The log record to format.

        Returns:
            str: The formatted log message.
        """
        # Base format
        formatted = f"[{record.levelname}] {record.getMessage()}"

        # Add structured fields compactly if present
        correlation_id = getattr(record, 'correlation_id', None)
        if correlation_id:
            formatted += f" [corr:{correlation_id}]"
        request_id = getattr(record, 'request_id', None)
        if request_id:
            formatted += f" [req:{request_id}]"

        # Add other structured fields
        extra_fields = []
        for key, value in record.__dict__.items():
            if key not in ('name', 'msg', 'args', 'levelname', 'levelno',
                          'pathname', 'filename', 'module', 'exc_info',
                          'exc_text', 'stack_info', 'lineno', 'funcName',
                          'created', 'msecs', 'relativeCreated', 'thread',
                          'threadName', 'processName', 'process', 'message',
                          'correlation_id', 'request_id'):
                extra_fields.append(f"{key}={value}")

        if extra_fields:
            formatted += f" {{{', '.join(extra_fields)}}}"

        return formatted


class JsonFormatter(logging.Formatter):
    """JSON log formatter."""

    def format(self, record):
        """Format the log record as JSON.

        Args:
            record: The log record to format.

        Returns:
            str: The JSON formatted log message.
        """
        # Base log entry
        log_entry = {
            'ts': datetime.datetime.fromtimestamp(record.created, tz=datetime.timezone.utc).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage()
        }

        # Add correlation and request IDs if available
        correlation_id = getattr(record, 'correlation_id', None)
        if correlation_id:
            log_entry['correlation_id'] = correlation_id

        request_id = getattr(record, 'request_id', None)
        if request_id:
            log_entry['request_id'] = request_id

        # Add other structured fields
        for key, value in record.__dict__.items():
            if key not in ('name', 'msg', 'args', 'levelname', 'levelno',
                          'pathname', 'filename', 'module', 'exc_info',
                          'exc_text', 'stack_info', 'lineno', 'funcName',
                          'created', 'msecs', 'relativeCreated', 'thread',
                          'threadName', 'processName', 'process', 'message',
                          'correlation_id', 'request_id') and value is not None:
                log_entry[key] = value

        return json.dumps(log_entry, default=str)


def is_debug_enabled(logger: logging.Logger) -> bool:
    """Check if DEBUG level is enabled for the logger.

    Args:
        logger (logging.Logger): The logger to check.

    Returns:
        bool: True if DEBUG is enabled.
    """
    return logger.isEnabledFor(logging.DEBUG)


def configure_logging():
    """Configure centralized logging for the application.

    Uses environment variables DEPGATE_LOG_LEVEL and DEPGATE_LOG_FORMAT.
    Default level is INFO, default format is 'human'.

    Caplog-friendly: preserve pytest's LogCaptureHandler if present, while
    ensuring a single depgate StreamHandler is attached.
    """
    # Get configuration from environment
    log_level_str = os.getenv('DEPGATE_LOG_LEVEL', 'INFO').upper()
    log_format = os.getenv('DEPGATE_LOG_FORMAT', 'human').lower()

    # Parse log level
    log_level = getattr(logging, log_level_str, logging.INFO)

    # Get root logger
    root_logger = logging.getLogger()

    # Preserve pytest caplog handlers if present
    kept_handlers = []
    for h in root_logger.handlers[:]:
        if h.__class__.__name__ == "LogCaptureHandler":
            kept_handlers.append(h)
        # Remove all handlers; we'll reattach kept caplog ones and our handler
        root_logger.removeHandler(h)

    # Reattach kept caplog handlers first
    for h in kept_handlers:
        root_logger.addHandler(h)

    # Create and attach single StreamHandler with selected formatter
    handler = logging.StreamHandler()
    formatter = JsonFormatter() if log_format == 'json' else HumanFormatter()
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Set root logger level
    root_logger.setLevel(log_level)


# Enriched logging helpers (scaffolding)
def log_discovered_files(logger, ecosystem, discovered) -> None:
    """DEBUG: Log discovered manifests and lockfiles."""
    try:
        logger.debug(
            "discovered_files ecosystem=%s manifests=%s lockfiles=%s",
            ecosystem,
            discovered.get("manifest"),
            discovered.get("lockfile"),
        )
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("discovered_files ecosystem=%s", ecosystem)


def log_selection(logger, ecosystem, manifest, lockfile, rationale: str) -> None:
    """DEBUG: Log chosen manifest/lockfile and rationale."""
    logger.debug(
        "selection ecosystem=%s manifest=%s lockfile=%s rationale=%s",
        ecosystem,
        manifest,
        lockfile,
        rationale,
    )


def warn_multiple_lockfiles(logger, ecosystem, chosen, alternatives) -> None:
    """WARN: Multiple lockfiles present; record chosen and alternatives."""
    logger.warning(
        "multiple_lockfiles ecosystem=%s chosen=%s alternatives=%s",
        ecosystem,
        chosen,
        alternatives,
    )


def warn_missing_expected(logger, ecosystem, expected) -> None:
    """WARN: Expected files missing."""
    logger.warning(
        "missing_expected_files ecosystem=%s expected=%s", ecosystem, expected
    )


def warn_orphan_lock_dep(logger, ecosystem, package, lockfile) -> None:
    """WARN: Dependency in lockfile not reachable from any manifest root."""
    logger.warning(
        "orphan_lock_dependency ecosystem=%s package=%s lockfile=%s",
        ecosystem,
        package,
        lockfile,
    )


def debug_dependency_line(logger, rec) -> None:
    """DEBUG: Per-dependency summary line for classification output."""
    try:
        origins = ";".join(
            f"{o.file_path}:{o.section}" for o in (getattr(rec, "source_files", []) or [])
        )
        logger.debug(
            "dependency ecosystem=%s name=%s version=%s relation=%s requirement=%s scope=%s origin=%s lockfile=%s",
            getattr(rec, "ecosystem", None),
            getattr(rec, "name", None),
            getattr(rec, "resolved_version", None),
            getattr(getattr(rec, "relation", None), "value", None),
            getattr(getattr(rec, "requirement", None), "value", None),
            getattr(getattr(rec, "scope", None), "value", None),
            origins,
            getattr(rec, "lockfile", None),
        )
    except Exception:  # pylint: disable=broad-exception-caught
        logger.debug("dependency name=%s", getattr(rec, "name", None))
