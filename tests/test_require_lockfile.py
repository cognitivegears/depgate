"""Tests for require-lockfile validation."""
from __future__ import annotations

import os
import tempfile
import json
import pytest
import sys

from constants import ExitCodes
from registry.npm.scan import scan_source as npm_scan_source
from registry.pypi.scan import scan_source as pypi_scan_source
from registry.nuget.scan import scan_source as nuget_scan_source


def test_npm_require_lockfile_with_lockfile():
    """Test that require-lockfile succeeds when lockfile exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create package.json
        package_json = {"dependencies": {"express": "^4.18.0"}}
        with open(os.path.join(tmpdir, "package.json"), "w") as f:
            json.dump(package_json, f)

        # Create package-lock.json
        package_lock = {
            "name": "test",
            "version": "1.0.0",
            "lockfileVersion": 2,
            "dependencies": {"express": {"version": "4.18.2"}}
        }
        with open(os.path.join(tmpdir, "package-lock.json"), "w") as f:
            json.dump(package_lock, f)

        # Should succeed with require_lockfile=True
        deps = npm_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=True)
        assert "express" in deps


def test_npm_require_lockfile_without_lockfile():
    """Test that require-lockfile fails when lockfile is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create package.json but no lockfile
        package_json = {"dependencies": {"express": "^4.18.0"}}
        with open(os.path.join(tmpdir, "package.json"), "w") as f:
            json.dump(package_json, f)

        # Should fail with require_lockfile=True
        with pytest.raises(SystemExit) as exc_info:
            npm_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=True)
        assert exc_info.value.code == ExitCodes.FILE_ERROR.value


def test_pypi_require_lockfile_with_lockfile():
    """Test that require-lockfile succeeds when lockfile exists for PyPI."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create pyproject.toml
        pyproject_content = """[project]
name = "test"
dependencies = ["requests>=2.28.0"]

[tool.uv]
"""
        with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
            f.write(pyproject_content)

        # Create uv.lock
        uv_lock_content = """version = 1
[[package]]
name = "requests"
version = "2.28.2"
"""
        with open(os.path.join(tmpdir, "uv.lock"), "w") as f:
            f.write(uv_lock_content)

        # Should succeed with require_lockfile=True
        deps = pypi_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=True)
        assert "requests" in deps


def test_pypi_require_lockfile_without_lockfile():
    """Test that require-lockfile fails when lockfile is missing for PyPI."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create pyproject.toml but no lockfile
        pyproject_content = """[project]
name = "test"
dependencies = ["requests>=2.28.0"]

[tool.uv]
"""
        with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
            f.write(pyproject_content)

        # Should fail with require_lockfile=True
        with pytest.raises(SystemExit) as exc_info:
            pypi_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=True)
        assert exc_info.value.code == ExitCodes.FILE_ERROR.value


def test_pypi_require_lockfile_with_requirements_txt():
    """Test that require-lockfile is ignored for requirements.txt (no lockfile support)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create requirements.txt (no lockfile support)
        with open(os.path.join(tmpdir, "requirements.txt"), "w") as f:
            f.write("requests>=2.28.0\n")

        # Should succeed even with require_lockfile=True (requirements.txt doesn't support lockfiles)
        deps = pypi_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=True)
        assert "requests" in deps


def test_nuget_require_lockfile_with_lockfile():
    """Test that require-lockfile succeeds when packages.lock.json exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create .csproj
        csproj_content = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />
  </ItemGroup>
</Project>
"""
        with open(os.path.join(tmpdir, "test.csproj"), "w") as f:
            f.write(csproj_content)

        # Create packages.lock.json
        with open(os.path.join(tmpdir, "packages.lock.json"), "w") as f:
            f.write("{}")

        # Should succeed with require_lockfile=True
        deps = nuget_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=True)
        assert "Newtonsoft.Json" in deps


def test_nuget_require_lockfile_without_lockfile():
    """Test that require-lockfile fails when packages.lock.json is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create .csproj but no lockfile
        csproj_content = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />
  </ItemGroup>
</Project>
"""
        with open(os.path.join(tmpdir, "test.csproj"), "w") as f:
            f.write(csproj_content)

        # Should fail with require_lockfile=True
        with pytest.raises(SystemExit) as exc_info:
            nuget_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=True)
        assert exc_info.value.code == ExitCodes.FILE_ERROR.value


def test_npm_require_lockfile_recursive():
    """Test require-lockfile with recursive scanning for npm."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create nested project structure
        subdir = os.path.join(tmpdir, "subproject")
        os.makedirs(subdir)

        # Root package.json with lockfile
        root_package = {"dependencies": {"express": "^4.18.0"}}
        with open(os.path.join(tmpdir, "package.json"), "w") as f:
            json.dump(root_package, f)
        root_lock = {"name": "root", "version": "1.0.0", "lockfileVersion": 2, "dependencies": {"express": {"version": "4.18.2"}}}
        with open(os.path.join(tmpdir, "package-lock.json"), "w") as f:
            json.dump(root_lock, f)

        # Subdirectory package.json without lockfile
        sub_package = {"dependencies": {"lodash": "^4.17.21"}}
        with open(os.path.join(subdir, "package.json"), "w") as f:
            json.dump(sub_package, f)

        # Should fail with require_lockfile=True (subdirectory missing lockfile)
        with pytest.raises(SystemExit) as exc_info:
            npm_scan_source(tmpdir, recursive=True, direct_only=False, require_lockfile=True)
        assert exc_info.value.code == ExitCodes.FILE_ERROR.value


def test_pypi_require_lockfile_recursive():
    """Test require-lockfile with recursive scanning for pypi."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create nested project structure
        subdir = os.path.join(tmpdir, "subproject")
        os.makedirs(subdir)

        # Root pyproject.toml with lockfile
        root_pyproject = """[project]
name = "root"
dependencies = ["requests>=2.28.0"]

[tool.uv]
"""
        with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
            f.write(root_pyproject)
        with open(os.path.join(tmpdir, "uv.lock"), "w") as f:
            f.write("version = 1\n[[package]]\nname = \"requests\"\nversion = \"2.28.2\"\n")

        # Subdirectory pyproject.toml without lockfile
        sub_pyproject = """[project]
name = "sub"
dependencies = ["click>=8.0.0"]

[tool.uv]
"""
        with open(os.path.join(subdir, "pyproject.toml"), "w") as f:
            f.write(sub_pyproject)

        # Should fail with require_lockfile=True (subdirectory missing lockfile)
        with pytest.raises(SystemExit) as exc_info:
            pypi_scan_source(tmpdir, recursive=True, direct_only=False, require_lockfile=True)
        assert exc_info.value.code == ExitCodes.FILE_ERROR.value
