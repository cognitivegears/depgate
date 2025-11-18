"""Additional tests for NuGet scanner to improve coverage."""
from __future__ import annotations

import os
import tempfile
import json
import pytest
import sys
import logging

from constants import ExitCodes
from registry.nuget.scan import scan_source as nuget_scan_source


def test_nuget_scan_packages_config():
    """Test scanning packages.config files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        packages_config_content = """<?xml version="1.0" encoding="utf-8"?>
<packages>
  <package id="Newtonsoft.Json" version="13.0.1" targetFramework="net48" />
  <package id="Serilog" version="2.12.0" targetFramework="net48" />
</packages>
"""
        with open(os.path.join(tmpdir, "packages.config"), "w") as f:
            f.write(packages_config_content)

        deps = nuget_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=False)
        assert "Newtonsoft.Json" in deps
        assert "Serilog" in deps


def test_nuget_scan_project_json():
    """Test scanning project.json files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_json = {
            "dependencies": {
                "Microsoft.NETCore.App": "1.0.0",
                "Newtonsoft.Json": "9.0.1"
            }
        }
        with open(os.path.join(tmpdir, "project.json"), "w") as f:
            json.dump(project_json, f)

        deps = nuget_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=False)
        assert "Microsoft.NETCore.App" in deps
        assert "Newtonsoft.Json" in deps


def test_nuget_scan_directory_build_props():
    """Test scanning Directory.Build.props files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        props_content = """<Project>
  <ItemGroup>
    <PackageReference Include="Microsoft.CodeAnalysis.NetAnalyzers" Version="7.0.0" />
    <PackageReference Include="StyleCop.Analyzers" Version="1.1.118" />
  </ItemGroup>
</Project>
"""
        with open(os.path.join(tmpdir, "Directory.Build.props"), "w") as f:
            f.write(props_content)

        deps = nuget_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=False)
        assert "Microsoft.CodeAnalysis.NetAnalyzers" in deps
        assert "StyleCop.Analyzers" in deps


def test_nuget_scan_recursive():
    """Test recursive scanning for NuGet."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Root .csproj
        root_csproj = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />
  </ItemGroup>
</Project>
"""
        with open(os.path.join(tmpdir, "root.csproj"), "w") as f:
            f.write(root_csproj)

        # Subdirectory .csproj
        subdir = os.path.join(tmpdir, "subproject")
        os.makedirs(subdir)
        sub_csproj = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Serilog" Version="2.12.0" />
  </ItemGroup>
</Project>
"""
        with open(os.path.join(subdir, "sub.csproj"), "w") as f:
            f.write(sub_csproj)

        deps = nuget_scan_source(tmpdir, recursive=True, direct_only=False, require_lockfile=False)
        assert "Newtonsoft.Json" in deps
        assert "Serilog" in deps


def test_nuget_scan_recursive_require_lockfile():
    """Test recursive scanning with require_lockfile."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Root .csproj with lockfile
        root_csproj = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />
  </ItemGroup>
</Project>
"""
        with open(os.path.join(tmpdir, "root.csproj"), "w") as f:
            f.write(root_csproj)
        with open(os.path.join(tmpdir, "packages.lock.json"), "w") as f:
            f.write("{}")

        # Subdirectory .csproj without lockfile
        subdir = os.path.join(tmpdir, "subproject")
        os.makedirs(subdir)
        sub_csproj = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Serilog" Version="2.12.0" />
  </ItemGroup>
</Project>
"""
        with open(os.path.join(subdir, "sub.csproj"), "w") as f:
            f.write(sub_csproj)

        # Should succeed because at least one lockfile exists
        deps = nuget_scan_source(tmpdir, recursive=True, direct_only=False, require_lockfile=True)
        assert "Newtonsoft.Json" in deps
        assert "Serilog" in deps


def test_nuget_scan_no_files_found():
    """Test error when no NuGet files are found."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Empty directory
        with pytest.raises(SystemExit) as exc_info:
            nuget_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=False)
        assert exc_info.value.code == ExitCodes.FILE_ERROR.value


def test_nuget_scan_invalid_csproj():
    """Test handling of invalid .csproj files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Invalid XML
        with open(os.path.join(tmpdir, "invalid.csproj"), "w") as f:
            f.write("<Project><Invalid XML>")

        # Should not crash, just skip invalid file
        deps = nuget_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=False)
        assert deps == []


def test_nuget_scan_invalid_packages_config():
    """Test handling of invalid packages.config files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Invalid XML
        with open(os.path.join(tmpdir, "packages.config"), "w") as f:
            f.write("<packages><Invalid XML>")

        # Should not crash, just skip invalid file
        deps = nuget_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=False)
        assert deps == []


def test_nuget_scan_invalid_project_json():
    """Test handling of invalid project.json files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Invalid JSON
        with open(os.path.join(tmpdir, "project.json"), "w") as f:
            f.write("{ invalid json }")

        # Should not crash, just skip invalid file
        deps = nuget_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=False)
        assert deps == []


def test_nuget_scan_project_json_no_dependencies():
    """Test project.json without dependencies key."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_json = {"name": "test", "version": "1.0.0"}
        with open(os.path.join(tmpdir, "project.json"), "w") as f:
            json.dump(project_json, f)

        deps = nuget_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=False)
        assert deps == []


def test_nuget_scan_csproj_with_namespace():
    """Test .csproj file with XML namespace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        csproj_content = """<?xml version="1.0" encoding="utf-8"?>
<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <ItemGroup>
    <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />
  </ItemGroup>
</Project>
"""
        with open(os.path.join(tmpdir, "test.csproj"), "w") as f:
            f.write(csproj_content)

        deps = nuget_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=False)
        assert "Newtonsoft.Json" in deps


def test_nuget_scan_packages_config_with_namespace():
    """Test packages.config file with XML namespace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        packages_config_content = """<?xml version="1.0" encoding="utf-8"?>
<packages xmlns="http://schemas.microsoft.com/packaging/2010/07/nuspec.xsd">
  <package id="Newtonsoft.Json" version="13.0.1" targetFramework="net48" />
</packages>
"""
        with open(os.path.join(tmpdir, "packages.config"), "w") as f:
            f.write(packages_config_content)

        deps = nuget_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=False)
        assert "Newtonsoft.Json" in deps


def test_nuget_scan_directory_build_props_with_namespace():
    """Test Directory.Build.props file with XML namespace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        props_content = """<?xml version="1.0" encoding="utf-8"?>
<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <ItemGroup>
    <PackageReference Include="Microsoft.CodeAnalysis.NetAnalyzers" Version="7.0.0" />
  </ItemGroup>
</Project>
"""
        with open(os.path.join(tmpdir, "Directory.Build.props"), "w") as f:
            f.write(props_content)

        deps = nuget_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=False)
        assert "Microsoft.CodeAnalysis.NetAnalyzers" in deps


def test_nuget_scan_recursive_require_lockfile_failure():
    """Test recursive require_lockfile fails when no lockfile found in any subdirectory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Root .csproj without lockfile
        root_csproj = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />
  </ItemGroup>
</Project>
"""
        with open(os.path.join(tmpdir, "root.csproj"), "w") as f:
            f.write(root_csproj)

        # Subdirectory .csproj without lockfile
        subdir = os.path.join(tmpdir, "subproject")
        os.makedirs(subdir)
        sub_csproj = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Serilog" Version="2.12.0" />
  </ItemGroup>
</Project>
"""
        with open(os.path.join(subdir, "sub.csproj"), "w") as f:
            f.write(sub_csproj)

        # Should fail with require_lockfile=True (no lockfile anywhere)
        with pytest.raises(SystemExit) as exc_info:
            nuget_scan_source(tmpdir, recursive=True, direct_only=False, require_lockfile=True)
        assert exc_info.value.code == ExitCodes.FILE_ERROR.value


def test_nuget_scan_directory_build_props_parse_error():
    """Test handling of parse error in Directory.Build.props."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Invalid XML
        with open(os.path.join(tmpdir, "Directory.Build.props"), "w") as f:
            f.write("<Project><Invalid XML>")

        # Should not crash, just skip invalid file
        deps = nuget_scan_source(tmpdir, recursive=False, direct_only=False, require_lockfile=False)
        assert deps == []


def test_nuget_scan_recursive_debug_logging():
    """Test recursive scanning with debug logging enabled."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Enable debug logging
        logger = logging.getLogger("registry.nuget.scan")
        original_level = logger.level
        logger.setLevel(logging.DEBUG)

        try:
            # Root .csproj
            root_csproj = """<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />
  </ItemGroup>
</Project>
"""
            with open(os.path.join(tmpdir, "root.csproj"), "w") as f:
                f.write(root_csproj)

            # Should trigger debug logging path
            deps = nuget_scan_source(tmpdir, recursive=True, direct_only=False, require_lockfile=False)
            assert "Newtonsoft.Json" in deps
        finally:
            logger.setLevel(original_level)
