"""Tests for MCP integration with direct-only and require-lockfile options."""
from __future__ import annotations

import os
import tempfile
import json
import pytest

from cli_mcp import _build_cli_args_for_project_scan


def test_mcp_direct_only_mapping():
    """Test that MCP includeTransitive maps correctly to direct_only."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # includeTransitive=False should map to direct_only=True
        args = _build_cli_args_for_project_scan(
            tmpdir, "npm", "compare", direct_only=True, require_lockfile=False
        )
        assert args.DIRECT_ONLY is True

        # includeTransitive=True should map to direct_only=False
        args = _build_cli_args_for_project_scan(
            tmpdir, "npm", "compare", direct_only=False, require_lockfile=False
        )
        assert args.DIRECT_ONLY is False

        # includeTransitive=None should use default (False)
        args = _build_cli_args_for_project_scan(
            tmpdir, "npm", "compare", direct_only=None, require_lockfile=False
        )
        assert args.DIRECT_ONLY is False  # Default from Constants


def test_mcp_require_lockfile_mapping():
    """Test that MCP requireLockfile maps correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # requireLockfile=True should map to REQUIRE_LOCKFILE=True
        args = _build_cli_args_for_project_scan(
            tmpdir, "npm", "compare", direct_only=False, require_lockfile=True
        )
        assert args.REQUIRE_LOCKFILE is True

        # requireLockfile=False should map to REQUIRE_LOCKFILE=False
        args = _build_cli_args_for_project_scan(
            tmpdir, "npm", "compare", direct_only=False, require_lockfile=False
        )
        assert args.REQUIRE_LOCKFILE is False

        # requireLockfile=None should use default (False)
        args = _build_cli_args_for_project_scan(
            tmpdir, "npm", "compare", direct_only=False, require_lockfile=None
        )
        assert args.REQUIRE_LOCKFILE is False  # Default from Constants
