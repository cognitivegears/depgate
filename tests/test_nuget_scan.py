"""Tests for NuGet source scanning functionality."""

import os
import tempfile
import xml.etree.ElementTree as ET
import json
import pytest

from registry.nuget.scan import scan_source


class TestScanCsproj:
    """Test .csproj file scanning."""

    def test_scans_package_reference(self):
        """Test scanning PackageReference elements from .csproj."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csproj_path = os.path.join(tmpdir, "TestProject.csproj")
            csproj_content = """<?xml version="1.0" encoding="utf-8"?>
<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />
    <PackageReference Include="Microsoft.Extensions.Logging" Version="7.0.0" />
  </ItemGroup>
</Project>"""
            with open(csproj_path, "w", encoding="utf-8") as f:
                f.write(csproj_content)

            packages = scan_source(tmpdir, recursive=False)

            assert "Newtonsoft.Json" in packages
            assert "Microsoft.Extensions.Logging" in packages

    def test_scans_recursively(self):
        """Test recursive scanning of .csproj files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = os.path.join(tmpdir, "subdir")
            os.makedirs(subdir)

            csproj1 = os.path.join(tmpdir, "Project1.csproj")
            csproj2 = os.path.join(subdir, "Project2.csproj")

            for path in [csproj1, csproj2]:
                with open(path, "w", encoding="utf-8") as f:
                    f.write("""<?xml version="1.0" encoding="utf-8"?>
<Project Sdk="Microsoft.NET.Sdk">
  <ItemGroup>
    <PackageReference Include="TestPackage" Version="1.0.0" />
  </ItemGroup>
</Project>""")

            packages = scan_source(tmpdir, recursive=True)

            assert "TestPackage" in packages
            # scan_source returns list(set(...)) which removes duplicates
            assert len([p for p in packages if p == "TestPackage"]) == 1  # Duplicates removed


class TestScanPackagesConfig:
    """Test packages.config file scanning."""

    def test_scans_packages_config(self):
        """Test scanning packages.config file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = os.path.join(tmpdir, "packages.config")
            config_content = """<?xml version="1.0" encoding="utf-8"?>
<packages>
  <package id="Newtonsoft.Json" version="13.0.1" targetFramework="net48" />
  <package id="Microsoft.Extensions.Logging" version="7.0.0" targetFramework="net48" />
</packages>"""
            with open(config_path, "w", encoding="utf-8") as f:
                f.write(config_content)

            packages = scan_source(tmpdir, recursive=False)

            assert "Newtonsoft.Json" in packages
            assert "Microsoft.Extensions.Logging" in packages


class TestScanProjectJson:
    """Test project.json file scanning."""

    def test_scans_project_json(self):
        """Test scanning project.json file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = os.path.join(tmpdir, "project.json")
            json_content = {
                "dependencies": {
                    "Newtonsoft.Json": "13.0.1",
                    "Microsoft.Extensions.Logging": "7.0.0"
                }
            }
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(json_content, f)

            packages = scan_source(tmpdir, recursive=False)

            assert "Newtonsoft.Json" in packages
            assert "Microsoft.Extensions.Logging" in packages


class TestScanDirectoryBuildProps:
    """Test Directory.Build.props file scanning."""

    def test_scans_directory_build_props(self):
        """Test scanning Directory.Build.props file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            props_path = os.path.join(tmpdir, "Directory.Build.props")
            props_content = """<?xml version="1.0" encoding="utf-8"?>
<Project>
  <ItemGroup>
    <PackageReference Include="Newtonsoft.Json" Version="13.0.1" />
  </ItemGroup>
</Project>"""
            with open(props_path, "w", encoding="utf-8") as f:
                f.write(props_content)

            packages = scan_source(tmpdir, recursive=False)

            assert "Newtonsoft.Json" in packages


class TestScanErrorHandling:
    """Test error handling in scanning."""

    def test_handles_missing_files_gracefully(self):
        """Test handling when no NuGet files are found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Empty directory
            with pytest.raises(SystemExit):
                scan_source(tmpdir, recursive=False)

    def test_handles_invalid_xml_gracefully(self):
        """Test handling of invalid XML files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csproj_path = os.path.join(tmpdir, "Invalid.csproj")
            with open(csproj_path, "w", encoding="utf-8") as f:
                f.write("<?xml version='1.0'?><invalid>")

            # Should not crash, but may return empty list or log warning
            packages = scan_source(tmpdir, recursive=False)
            # Result depends on implementation, but should not raise exception

    def test_handles_invalid_json_gracefully(self):
        """Test handling of invalid JSON files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path = os.path.join(tmpdir, "project.json")
            with open(json_path, "w", encoding="utf-8") as f:
                f.write("{ invalid json }")

            # Should not crash
            packages = scan_source(tmpdir, recursive=False)
            # Result depends on implementation, but should not raise exception
