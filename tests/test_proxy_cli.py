"""Tests for proxy CLI helpers."""

import pytest

from src.cli_proxy import _is_local_bind_host, _enforce_local_binding


def test_is_local_bind_host_loopback():
    """Loopback hosts should be treated as local."""
    assert _is_local_bind_host("127.0.0.1") is True
    assert _is_local_bind_host("localhost") is True
    assert _is_local_bind_host("::1") is True


def test_is_local_bind_host_external():
    """Non-local hosts should be treated as external."""
    assert _is_local_bind_host("0.0.0.0") is False
    assert _is_local_bind_host("192.168.1.10") is False


def test_enforce_local_binding_rejects_external():
    """External bindings must be explicitly allowed."""
    with pytest.raises(SystemExit):
        _enforce_local_binding("0.0.0.0", False)


def test_enforce_local_binding_allows_with_flag():
    """External bindings are allowed only when flag is set."""
    _enforce_local_binding("0.0.0.0", True)
