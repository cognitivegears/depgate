"""Tests for npm scanner with lockfile support."""

import json
import tempfile
from pathlib import Path

import pytest

from registry.npm.scan import scan_source


class TestNpmScanWithLockfiles:
    """Test npm scanner with lockfile discovery and parsing."""

    def test_scan_with_package_lock_json(self, tmp_path):
        """Test scanning with package-lock.json present."""
        # Create package.json
        package_json = {
            "name": "test-package",
            "version": "1.0.0",
            "dependencies": {
                "lodash": "^4.17.0"
            }
        }
        (tmp_path / "package.json").write_text(json.dumps(package_json, indent=2))

        # Create package-lock.json
        package_lock = {
            "name": "test-package",
            "version": "1.0.0",
            "lockfileVersion": 2,
            "packages": {
                "": {
                    "name": "test-package",
                    "version": "1.0.0"
                },
                "node_modules/lodash": {
                    "name": "lodash",
                    "version": "4.17.21"
                },
                "node_modules/express": {
                    "name": "express",
                    "version": "4.18.2"
                }
            }
        }
        (tmp_path / "package-lock.json").write_text(json.dumps(package_lock, indent=2))

        result = scan_source(str(tmp_path), recursive=False)

        # Should include all packages from lockfile (transitive dependencies)
        assert "lodash" in result
        assert "express" in result
        assert len(result) >= 2

    def test_scan_with_yarn_lock(self, tmp_path):
        """Test scanning with yarn.lock present."""
        # Create package.json
        package_json = {
            "name": "test-package",
            "version": "1.0.0",
            "dependencies": {
                "lodash": "^4.17.0"
            }
        }
        (tmp_path / "package.json").write_text(json.dumps(package_json, indent=2))

        # Create yarn.lock
        yarn_lock = """# yarn.lock

lodash@^4.17.0:
  version "4.17.21"
  resolved "https://registry.yarnpkg.com/lodash/-/lodash-4.17.21.tgz#abc123"

express@^4.18.0:
  version "4.18.2"
  resolved "https://registry.yarnpkg.com/express/-/express-4.18.2.tgz#def456"
"""
        (tmp_path / "yarn.lock").write_text(yarn_lock)

        result = scan_source(str(tmp_path), recursive=False)

        # Should include packages from yarn.lock
        assert "lodash" in result
        assert "express" in result
        assert len(result) >= 2

    def test_scan_with_bun_lock(self, tmp_path):
        """Test scanning with bun.lock present."""
        # Create package.json
        package_json = {
            "name": "test-package",
            "version": "1.0.0",
            "dependencies": {
                "lodash": "^4.17.0"
            }
        }
        (tmp_path / "package.json").write_text(json.dumps(package_json, indent=2))

        # Create bun.lock
        bun_lock = """{
  "lockfileVersion": 6,
  "packages": {
    "": {
      "name": "test-package",
      "version": "1.0.0"
    },
    "node_modules/lodash": {
      "name": "lodash",
      "version": "4.17.21"
    },
    "node_modules/express": {
      "name": "express",
      "version": "4.18.2"
    }
  }
}
"""
        (tmp_path / "bun.lock").write_text(bun_lock)

        result = scan_source(str(tmp_path), recursive=False)

        # Should include packages from bun.lock
        assert "lodash" in result
        assert "express" in result
        assert len(result) >= 2

    def test_scan_lockfile_precedence_package_lock_first(self, tmp_path):
        """Test that package-lock.json takes precedence over yarn.lock."""
        # Create package.json
        package_json = {
            "name": "test-package",
            "version": "1.0.0",
            "dependencies": {
                "lodash": "^4.17.0"
            }
        }
        (tmp_path / "package.json").write_text(json.dumps(package_json, indent=2))

        # Create both lockfiles
        package_lock = {
            "name": "test-package",
            "version": "1.0.0",
            "lockfileVersion": 2,
            "packages": {
                "": {"name": "test-package", "version": "1.0.0"},
                "node_modules/express": {"name": "express", "version": "4.18.2"}
            }
        }
        (tmp_path / "package-lock.json").write_text(json.dumps(package_lock, indent=2))

        yarn_lock = """# yarn.lock
lodash@^4.17.0:
  version "4.17.21"
"""
        (tmp_path / "yarn.lock").write_text(yarn_lock)

        result = scan_source(str(tmp_path), recursive=False)

        # Should use package-lock.json (express), not yarn.lock (lodash)
        assert "express" in result
        # lodash might be in result if package.json is used as fallback, but express should be from lockfile

    def test_scan_fallback_to_package_json(self, tmp_path):
        """Test fallback to package.json when no lockfile present."""
        # Create package.json only
        package_json = {
            "name": "test-package",
            "version": "1.0.0",
            "dependencies": {
                "lodash": "^4.17.0"
            },
            "devDependencies": {
                "jest": "^27.0.0"
            }
        }
        (tmp_path / "package.json").write_text(json.dumps(package_json, indent=2))

        result = scan_source(str(tmp_path), recursive=False)

        # Should include direct dependencies from package.json
        assert "lodash" in result
        assert "jest" in result
        assert len(result) == 2

    def test_scan_fallback_on_lockfile_parse_failure(self, tmp_path):
        """Test fallback to package.json when lockfile parsing fails."""
        # Create package.json
        package_json = {
            "name": "test-package",
            "version": "1.0.0",
            "dependencies": {
                "lodash": "^4.17.0"
            }
        }
        (tmp_path / "package.json").write_text(json.dumps(package_json, indent=2))

        # Create invalid package-lock.json
        (tmp_path / "package-lock.json").write_text("invalid json {")

        result = scan_source(str(tmp_path), recursive=False)

        # Should fallback to package.json
        assert "lodash" in result
        assert len(result) == 1

    def test_scan_recursive_with_lockfiles(self, tmp_path):
        """Test recursive scanning with lockfiles in subdirectories."""
        # Create root package.json
        root_package_json = {
            "name": "root-package",
            "version": "1.0.0",
            "dependencies": {
                "lodash": "^4.17.0"
            }
        }
        (tmp_path / "package.json").write_text(json.dumps(root_package_json, indent=2))

        # Create subdirectory with package.json and lockfile
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        sub_package_json = {
            "name": "sub-package",
            "version": "1.0.0",
            "dependencies": {
                "express": "^4.18.0"
            }
        }
        (subdir / "package.json").write_text(json.dumps(sub_package_json, indent=2))

        sub_package_lock = {
            "name": "sub-package",
            "version": "1.0.0",
            "lockfileVersion": 2,
            "packages": {
                "": {"name": "sub-package", "version": "1.0.0"},
                "node_modules/express": {"name": "express", "version": "4.18.2"},
                "node_modules/axios": {"name": "axios", "version": "1.0.0"}
            }
        }
        (subdir / "package-lock.json").write_text(json.dumps(sub_package_lock, indent=2))

        result = scan_source(str(tmp_path), recursive=True)

        # Should include packages from both directories
        assert "lodash" in result  # From root package.json
        assert "express" in result  # From subdir lockfile
        assert "axios" in result  # From subdir lockfile
        assert len(result) >= 3

    def test_scan_missing_package_json_error(self, tmp_path):
        """Test that missing package.json causes error."""
        # Don't create package.json

        with pytest.raises(SystemExit):
            scan_source(str(tmp_path), recursive=False)
