"""Tests for PyPI scanner with lockfile support."""

from pathlib import Path

import pytest

from registry.pypi.scan import scan_source


class TestPypiScanWithLockfiles:
    """Test PyPI scanner with lockfile discovery and parsing."""

    def test_scan_with_uv_lock(self, tmp_path):
        """Test scanning with uv.lock present."""
        # Create pyproject.toml
        pyproject_content = """[project]
name = "test-package"
version = "1.0.0"
dependencies = [
    "requests>=2.28.0"
]
"""
        (tmp_path / "pyproject.toml").write_text(pyproject_content, encoding="utf-8")

        # Create uv.lock
        uv_lock_content = """version = 1

[[package]]
name = "requests"
version = "2.28.2"
dependencies = [
    { name = "certifi" },
    { name = "urllib3" },
]

[[package]]
name = "certifi"
version = "2022.12.7"

[[package]]
name = "urllib3"
version = "1.26.14"
"""
        (tmp_path / "uv.lock").write_text(uv_lock_content, encoding="utf-8")

        result = scan_source(str(tmp_path), recursive=False)

        # Should include all packages from lockfile (transitive dependencies)
        assert "requests" in result
        assert "certifi" in result
        assert "urllib3" in result
        assert len(result) == 3

    def test_scan_with_poetry_lock(self, tmp_path):
        """Test scanning with poetry.lock present."""
        # Create pyproject.toml
        pyproject_content = """[project]
name = "test-package"
version = "1.0.0"
dependencies = [
    "requests>=2.28.0"
]
"""
        (tmp_path / "pyproject.toml").write_text(pyproject_content, encoding="utf-8")

        # Create poetry.lock
        poetry_lock_content = """[[package]]
name = "requests"
version = "2.28.2"
dependencies = [
    { name = "certifi" },
    { name = "urllib3" },
]

[[package]]
name = "certifi"
version = "2022.12.7"

[[package]]
name = "urllib3"
version = "1.26.14"
"""
        (tmp_path / "poetry.lock").write_text(poetry_lock_content, encoding="utf-8")

        result = scan_source(str(tmp_path), recursive=False)

        # Should include all packages from lockfile
        assert "requests" in result
        assert "certifi" in result
        assert "urllib3" in result
        assert len(result) == 3

    def test_scan_fallback_to_manifest(self, tmp_path):
        """Test fallback to pyproject.toml when no lockfile present."""
        # Create pyproject.toml only
        pyproject_content = """[project]
name = "test-package"
version = "1.0.0"
dependencies = [
    "requests>=2.28.0"
]
"""
        (tmp_path / "pyproject.toml").write_text(pyproject_content, encoding="utf-8")

        result = scan_source(str(tmp_path), recursive=False)

        # Should include direct dependencies from pyproject.toml
        assert "requests" in result
        assert len(result) == 1

    def test_scan_fallback_on_lockfile_parse_failure(self, tmp_path):
        """Test fallback to manifest when lockfile parsing fails."""
        # Create pyproject.toml
        pyproject_content = """[project]
name = "test-package"
version = "1.0.0"
dependencies = [
    "requests>=2.28.0"
]
"""
        (tmp_path / "pyproject.toml").write_text(pyproject_content, encoding="utf-8")

        # Create invalid uv.lock
        (tmp_path / "uv.lock").write_text("invalid toml {", encoding="utf-8")

        result = scan_source(str(tmp_path), recursive=False)

        # Should fallback to pyproject.toml
        assert "requests" in result
        assert len(result) == 1

    def test_scan_recursive_with_lockfiles(self, tmp_path):
        """Test recursive scanning with lockfiles in subdirectories."""
        # Create root pyproject.toml
        root_pyproject = """[project]
name = "root-package"
version = "1.0.0"
dependencies = [
    "requests>=2.28.0"
]
"""
        (tmp_path / "pyproject.toml").write_text(root_pyproject, encoding="utf-8")

        # Create subdirectory with pyproject.toml and uv.lock
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        sub_pyproject = """[project]
name = "sub-package"
version = "1.0.0"
dependencies = [
    "flask>=2.0.0"
]
"""
        (subdir / "pyproject.toml").write_text(sub_pyproject, encoding="utf-8")

        sub_uv_lock = """version = 1

[[package]]
name = "flask"
version = "2.0.0"
dependencies = [
    { name = "werkzeug" },
]

[[package]]
name = "werkzeug"
version = "2.0.0"
"""
        (subdir / "uv.lock").write_text(sub_uv_lock, encoding="utf-8")

        result = scan_source(str(tmp_path), recursive=True)

        # Should include packages from both directories
        assert "requests" in result  # From root pyproject.toml
        assert "flask" in result  # From subdir lockfile
        assert "werkzeug" in result  # From subdir lockfile (transitive)
        assert len(result) >= 3

    def test_scan_lockfile_precedence_uv_first(self, tmp_path):
        """Test that uv.lock takes precedence over poetry.lock when tool.uv is present."""
        # Create pyproject.toml with tool.uv
        pyproject_content = """[project]
name = "test-package"
version = "1.0.0"
dependencies = [
    "requests>=2.28.0"
]

[tool.uv]
"""
        (tmp_path / "pyproject.toml").write_text(pyproject_content, encoding="utf-8")

        # Create both lockfiles
        uv_lock = """version = 1

[[package]]
name = "requests"
version = "2.28.2"
"""
        (tmp_path / "uv.lock").write_text(uv_lock, encoding="utf-8")

        poetry_lock = """[[package]]
name = "flask"
version = "2.0.0"
"""
        (tmp_path / "poetry.lock").write_text(poetry_lock, encoding="utf-8")

        result = scan_source(str(tmp_path), recursive=False)

        # Should use uv.lock (requests), not poetry.lock (flask)
        assert "requests" in result
        assert "flask" not in result
