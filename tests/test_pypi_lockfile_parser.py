"""Tests for PyPI lockfile parsers (uv.lock, poetry.lock)."""

from registry.pypi.lockfile_parser import parse_uv_lock, parse_poetry_lock


class TestUvLockParser:
    """Test uv.lock parser."""

    def test_parse_uv_lock_basic(self, tmp_path):
        """Test parsing basic uv.lock file."""
        uv_lock_content = """version = 1

[[package]]
name = "requests"
version = "2.28.2"
dependencies = [
    { name = "certifi" },
    { name = "charset-normalizer" },
    { name = "idna" },
    { name = "urllib3" },
]

[[package]]
name = "certifi"
version = "2022.12.7"

[[package]]
name = "charset-normalizer"
version = "3.0.1"

[[package]]
name = "idna"
version = "3.4"

[[package]]
name = "urllib3"
version = "1.26.14"
"""
        lockfile_path = tmp_path / "uv.lock"
        lockfile_path.write_text(uv_lock_content, encoding="utf-8")

        result = parse_uv_lock(str(lockfile_path))

        assert "requests" in result
        assert "certifi" in result
        assert "charset-normalizer" in result
        assert "idna" in result
        assert "urllib3" in result
        assert len(result) == 5

    def test_parse_uv_lock_missing_file(self, tmp_path):
        """Test parsing non-existent file returns empty list."""
        result = parse_uv_lock(str(tmp_path / "nonexistent.lock"))
        assert result == []

    def test_parse_uv_lock_invalid_toml(self, tmp_path):
        """Test parsing invalid TOML returns empty list."""
        lockfile_path = tmp_path / "uv.lock"
        lockfile_path.write_text("invalid toml {", encoding="utf-8")

        result = parse_uv_lock(str(lockfile_path))
        assert result == []

    def test_parse_uv_lock_no_package_section(self, tmp_path):
        """Test parsing uv.lock without package section."""
        uv_lock_content = """version = 1
"""
        lockfile_path = tmp_path / "uv.lock"
        lockfile_path.write_text(uv_lock_content, encoding="utf-8")

        result = parse_uv_lock(str(lockfile_path))
        assert result == []

    def test_parse_uv_lock_package_without_name(self, tmp_path):
        """Test parsing uv.lock with package missing name field."""
        uv_lock_content = """version = 1

[[package]]
version = "2.28.2"

[[package]]
name = "requests"
version = "2.28.2"
"""
        lockfile_path = tmp_path / "uv.lock"
        lockfile_path.write_text(uv_lock_content, encoding="utf-8")

        result = parse_uv_lock(str(lockfile_path))

        # Should only include packages with name field
        assert "requests" in result
        assert len(result) == 1


class TestPoetryLockParser:
    """Test poetry.lock parser."""

    def test_parse_poetry_lock_basic(self, tmp_path):
        """Test parsing basic poetry.lock file."""
        poetry_lock_content = """[[package]]
name = "requests"
version = "2.28.2"
dependencies = [
    { name = "certifi", version = ">=2022.12.7" },
    { name = "charset-normalizer", version = ">=3.0.1" },
    { name = "idna", version = ">=3.4" },
    { name = "urllib3", version = ">=1.26.14" },
]

[[package]]
name = "certifi"
version = "2022.12.7"

[[package]]
name = "charset-normalizer"
version = "3.0.1"

[[package]]
name = "idna"
version = "3.4"

[[package]]
name = "urllib3"
version = "1.26.14"
"""
        lockfile_path = tmp_path / "poetry.lock"
        lockfile_path.write_text(poetry_lock_content, encoding="utf-8")

        result = parse_poetry_lock(str(lockfile_path))

        assert "requests" in result
        assert "certifi" in result
        assert "charset-normalizer" in result
        assert "idna" in result
        assert "urllib3" in result
        assert len(result) == 5

    def test_parse_poetry_lock_missing_file(self, tmp_path):
        """Test parsing non-existent file returns empty list."""
        result = parse_poetry_lock(str(tmp_path / "nonexistent.lock"))
        assert result == []

    def test_parse_poetry_lock_invalid_toml(self, tmp_path):
        """Test parsing invalid TOML returns empty list."""
        lockfile_path = tmp_path / "poetry.lock"
        lockfile_path.write_text("invalid toml {", encoding="utf-8")

        result = parse_poetry_lock(str(lockfile_path))
        assert result == []

    def test_parse_poetry_lock_no_package_section(self, tmp_path):
        """Test parsing poetry.lock without package section."""
        poetry_lock_content = """# poetry.lock
"""
        lockfile_path = tmp_path / "poetry.lock"
        lockfile_path.write_text(poetry_lock_content, encoding="utf-8")

        result = parse_poetry_lock(str(lockfile_path))
        assert result == []

    def test_parse_poetry_lock_package_without_name(self, tmp_path):
        """Test parsing poetry.lock with package missing name field."""
        poetry_lock_content = """[[package]]
version = "2.28.2"

[[package]]
name = "requests"
version = "2.28.2"
"""
        lockfile_path = tmp_path / "poetry.lock"
        lockfile_path.write_text(poetry_lock_content, encoding="utf-8")

        result = parse_poetry_lock(str(lockfile_path))

        # Should only include packages with name field
        assert "requests" in result
        assert len(result) == 1
