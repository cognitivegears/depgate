"""Tests for direct-only dependency scanning mode."""
from __future__ import annotations

import os
import tempfile
import json

from registry.npm.scan import scan_source as npm_scan_source
from registry.pypi.scan import scan_source as pypi_scan_source
from registry.nuget.scan import scan_source as nuget_scan_source
from registry.maven.client import scan_source as maven_scan_source


def test_npm_direct_only_with_lockfile():
    """Test that direct-only mode uses package.json even when lockfile exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create package.json with direct dependencies
        package_json = {
            "dependencies": {
                "express": "^4.18.0",
                "lodash": "^4.17.21"
            },
            "devDependencies": {
                "jest": "^29.0.0"
            }
        }
        with open(os.path.join(tmpdir, "package.json"), "w") as f:
            json.dump(package_json, f)

        # Create package-lock.json with transitive dependencies
        package_lock = {
            "name": "test",
            "version": "1.0.0",
            "lockfileVersion": 2,
            "dependencies": {
                "express": {
                    "version": "4.18.2",
                    "dependencies": {
                        "accepts": {"version": "1.3.8"},
                        "array-flatten": {"version": "1.1.1"}
                    }
                },
                "lodash": {"version": "4.17.21"},
                "jest": {"version": "29.7.0"}
            }
        }
        with open(os.path.join(tmpdir, "package-lock.json"), "w") as f:
            json.dump(package_lock, f)

        # Test direct-only mode: should only return direct deps
        deps_direct = npm_scan_source(tmpdir, recursive=False, direct_only=True, require_lockfile=False)
        assert set(deps_direct) == {"express", "lodash", "jest"}

        # Test normal mode: should return all deps from lockfile
        deps_all = npm_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=False)
        assert "express" in deps_all
        assert "lodash" in deps_all
        assert "jest" in deps_all
        # Should also include transitive deps
        assert "accepts" in deps_all or "array-flatten" in deps_all


def test_pypi_direct_only_with_lockfile():
    """Test that direct-only mode uses manifest even when lockfile exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create pyproject.toml with direct dependencies
        pyproject_content = """[project]
name = "test"
dependencies = [
    "requests>=2.28.0",
    "click>=8.0.0"
]

[tool.uv]
"""
        with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
            f.write(pyproject_content)

        # Create uv.lock with transitive dependencies (simplified)
        uv_lock_content = """version = 1
[[package]]
name = "requests"
version = "2.28.2"
dependencies = [
    { name = "urllib3", version = "1.26.14" },
    { name = "certifi", version = "2022.12.7" }
]

[[package]]
name = "click"
version = "8.1.3"

[[package]]
name = "urllib3"
version = "1.26.14"

[[package]]
name = "certifi"
version = "2022.12.7"
"""
        with open(os.path.join(tmpdir, "uv.lock"), "w") as f:
            f.write(uv_lock_content)

        # Test direct-only mode: should only return direct deps
        deps_direct = pypi_scan_source(tmpdir, recursive=False, direct_only=True, require_lockfile=False)
        assert set(deps_direct) == {"requests", "click"}

        # Test normal mode: should return all deps from lockfile
        deps_all = pypi_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=False)
        assert "requests" in deps_all
        assert "click" in deps_all
        # Should also include transitive deps
        assert "urllib3" in deps_all or "certifi" in deps_all


def test_nuget_direct_only():
    """Test that direct-only mode works for NuGet (already default behavior)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a simple .csproj file
        csproj_content = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />
    <PackageReference Include="Serilog" Version="2.12.0" />
  </ItemGroup>
</Project>
"""
        with open(os.path.join(tmpdir, "test.csproj"), "w") as f:
            f.write(csproj_content)

        # NuGet always scans direct dependencies only (no lockfile parsing)
        deps = nuget_scan_source(tmpdir, recursive=False, direct_only=True, require_lockfile=False)
        assert set(deps) == {"Newtonsoft.Json", "Serilog"}


def test_maven_direct_only():
    """Test that direct-only mode works for Maven (already default behavior)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a simple pom.xml
        pom_content = """<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>test</artifactId>
  <version>1.0.0</version>
  <dependencies>
    <dependency>
      <groupId>junit</groupId>
      <artifactId>junit</artifactId>
      <version>4.13.2</version>
    </dependency>
    <dependency>
      <groupId>org.mockito</groupId>
      <artifactId>mockito-core</artifactId>
      <version>4.11.0</version>
    </dependency>
  </dependencies>
</project>
"""
        with open(os.path.join(tmpdir, "pom.xml"), "w") as f:
            f.write(pom_content)

        # Maven always scans direct dependencies only
        deps = maven_scan_source(tmpdir, recursive=False, direct_only=True, require_lockfile=False)
        assert set(deps) == {"junit:junit", "org.mockito:mockito-core"}


def test_npm_direct_only_recursive():
    """Test direct-only mode with recursive scanning for npm."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create nested project structure
        subdir = os.path.join(tmpdir, "subproject")
        os.makedirs(subdir)

        # Root package.json
        root_package = {"dependencies": {"express": "^4.18.0"}}
        with open(os.path.join(tmpdir, "package.json"), "w") as f:
            json.dump(root_package, f)

        # Subdirectory package.json
        sub_package = {"dependencies": {"lodash": "^4.17.21"}}
        with open(os.path.join(subdir, "package.json"), "w") as f:
            json.dump(sub_package, f)

        # Test direct-only recursive mode
        deps = npm_scan_source(tmpdir, recursive=True, direct_only=True, require_lockfile=False)
        assert "express" in deps
        assert "lodash" in deps


def test_pypi_direct_only_recursive():
    """Test direct-only mode with recursive scanning for pypi."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create nested project structure
        subdir = os.path.join(tmpdir, "subproject")
        os.makedirs(subdir)

        # Root pyproject.toml
        root_pyproject = """[project]
name = "root"
dependencies = ["requests>=2.28.0"]
"""
        with open(os.path.join(tmpdir, "pyproject.toml"), "w") as f:
            f.write(root_pyproject)

        # Subdirectory pyproject.toml
        sub_pyproject = """[project]
name = "sub"
dependencies = ["click>=8.0.0"]
"""
        with open(os.path.join(subdir, "pyproject.toml"), "w") as f:
            f.write(sub_pyproject)

        # Test direct-only recursive mode
        deps = pypi_scan_source(tmpdir, recursive=True, direct_only=True, require_lockfile=False)
        assert "requests" in deps
        assert "click" in deps
