"""Tests for MCP integration with direct-only and require-lockfile options."""
from __future__ import annotations

import os
import tempfile
import json
import pytest

from cli_mcp import _build_cli_args_for_project_scan, _run_scan_pipeline
from cli_build import build_pkglist


def test_mcp_direct_only_mapping():
    """Test that MCP includeTransitive maps correctly to direct_only and is passed as runtime parameter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a test package.json
        package_json = {"dependencies": {"express": "^4.18.0"}}
        with open(os.path.join(tmpdir, "package.json"), "w") as f:
            json.dump(package_json, f)

        # Create package-lock.json with transitive deps
        package_lock = {
            "name": "test",
            "version": "1.0.0",
            "lockfileVersion": 2,
            "dependencies": {
                "express": {
                    "version": "4.18.2",
                    "dependencies": {"accepts": {"version": "1.3.8"}}
                }
            }
        }
        with open(os.path.join(tmpdir, "package-lock.json"), "w") as f:
            json.dump(package_lock, f)

        # Build args (direct_only/require_lockfile are now runtime params, not in args)
        args = _build_cli_args_for_project_scan(
            tmpdir, "npm", "compare", direct_only=None, require_lockfile=None
        )

        # Test that direct_only=True (includeTransitive=False) only gets direct deps
        pkglist_direct = build_pkglist(args, direct_only=True, require_lockfile=False)
        assert "express" in pkglist_direct
        assert "accepts" not in pkglist_direct  # Transitive dependency excluded

        # Test that direct_only=False (includeTransitive=True) gets all deps
        pkglist_all = build_pkglist(args, direct_only=False, require_lockfile=False)
        assert "express" in pkglist_all
        assert "accepts" in pkglist_all  # Transitive dependency included


def test_mcp_require_lockfile_mapping():
    """Test that MCP requireLockfile is passed as runtime parameter."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a test package.json
        package_json = {"dependencies": {"express": "^4.18.0"}}
        with open(os.path.join(tmpdir, "package.json"), "w") as f:
            json.dump(package_json, f)

        # Build args
        args = _build_cli_args_for_project_scan(
            tmpdir, "npm", "compare", direct_only=None, require_lockfile=None
        )

        # Test that require_lockfile=True fails when lockfile is missing
        with pytest.raises(SystemExit):
            build_pkglist(args, direct_only=False, require_lockfile=True)

        # Create lockfile and test it works
        package_lock = {
            "name": "test",
            "version": "1.0.0",
            "lockfileVersion": 2,
            "dependencies": {"express": {"version": "4.18.2"}}
        }
        with open(os.path.join(tmpdir, "package-lock.json"), "w") as f:
            json.dump(package_lock, f)

        # Should succeed with lockfile present
        pkglist = build_pkglist(args, direct_only=False, require_lockfile=True)
        assert "express" in pkglist
