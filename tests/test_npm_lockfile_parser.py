"""Tests for npm lockfile parsers (package-lock.json, yarn.lock, bun.lock)."""

import json
import tempfile
from pathlib import Path

import pytest

from registry.npm.lockfile_parser import (
    parse_package_lock,
    parse_yarn_lock,
    parse_bun_lock,
    _strip_jsonc_comments,
)


class TestPackageLockParser:
    """Test package-lock.json parser."""

    def test_parse_package_lock_v1(self, tmp_path):
        """Test parsing package-lock.json with lockfileVersion 1."""
        lockfile_content = {
            "name": "test-package",
            "version": "1.0.0",
            "lockfileVersion": 1,
            "dependencies": {
                "lodash": {
                    "version": "4.17.21",
                    "resolved": "https://registry.npmjs.org/lodash/-/lodash-4.17.21.tgz",
                    "dependencies": {
                        "underscore": {
                            "version": "1.13.0",
                            "resolved": "https://registry.npmjs.org/underscore/-/underscore-1.13.0.tgz",
                        }
                    }
                },
                "express": {
                    "version": "4.18.2",
                    "resolved": "https://registry.npmjs.org/express/-/express-4.18.2.tgz",
                }
            }
        }

        lockfile_path = tmp_path / "package-lock.json"
        lockfile_path.write_text(json.dumps(lockfile_content, indent=2))

        result = parse_package_lock(str(lockfile_path))

        assert "lodash" in result
        assert "express" in result
        assert "underscore" in result
        assert len(result) == 3

    def test_parse_package_lock_v2(self, tmp_path):
        """Test parsing package-lock.json with lockfileVersion 2."""
        lockfile_content = {
            "name": "test-package",
            "version": "1.0.0",
            "lockfileVersion": 2,
            "packages": {
                "": {
                    "name": "test-package",
                    "version": "1.0.0"
                },
                "node_modules/lodash": {
                    "version": "4.17.21",
                    "resolved": "https://registry.npmjs.org/lodash/-/lodash-4.17.21.tgz"
                },
                "node_modules/express": {
                    "version": "4.18.2",
                    "resolved": "https://registry.npmjs.org/express/-/express-4.18.2.tgz"
                },
                "node_modules/@types/node": {
                    "version": "18.0.0",
                    "resolved": "https://registry.npmjs.org/@types/node/-/node-18.0.0.tgz"
                }
            }
        }

        lockfile_path = tmp_path / "package-lock.json"
        lockfile_path.write_text(json.dumps(lockfile_content, indent=2))

        result = parse_package_lock(str(lockfile_path))

        assert "lodash" in result
        assert "express" in result
        assert "@types/node" in result
        assert len(result) == 3  # Root package excluded

    def test_parse_package_lock_v3(self, tmp_path):
        """Test parsing package-lock.json with lockfileVersion 3."""
        lockfile_content = {
            "name": "test-package",
            "version": "1.0.0",
            "lockfileVersion": 3,
            "packages": {
                "": {
                    "name": "test-package",
                    "version": "1.0.0"
                },
                "node_modules/lodash": {
                    "name": "lodash",
                    "version": "4.17.21",
                    "resolved": "https://registry.npmjs.org/lodash/-/lodash-4.17.21.tgz"
                },
                "node_modules/express": {
                    "name": "express",
                    "version": "4.18.2",
                    "resolved": "https://registry.npmjs.org/express/-/express-4.18.2.tgz"
                }
            }
        }

        lockfile_path = tmp_path / "package-lock.json"
        lockfile_path.write_text(json.dumps(lockfile_content, indent=2))

        result = parse_package_lock(str(lockfile_path))

        assert "lodash" in result
        assert "express" in result
        assert len(result) == 2

    def test_parse_package_lock_v2_scoped_packages(self, tmp_path):
        """Test parsing scoped packages in v2 format."""
        lockfile_content = {
            "name": "test-package",
            "version": "1.0.0",
            "lockfileVersion": 2,
            "packages": {
                "": {
                    "name": "test-package",
                    "version": "1.0.0"
                },
                "node_modules/@types/node": {
                    "version": "18.0.0"
                },
                "node_modules/@scope/package": {
                    "version": "1.0.0"
                }
            }
        }

        lockfile_path = tmp_path / "package-lock.json"
        lockfile_path.write_text(json.dumps(lockfile_content, indent=2))

        result = parse_package_lock(str(lockfile_path))

        assert "@types/node" in result
        assert "@scope/package" in result
        assert len(result) == 2

    def test_parse_package_lock_v2_without_name_field(self, tmp_path):
        """Test parsing v2 when packages don't have 'name' field (extract from path)."""
        lockfile_content = {
            "name": "test-package",
            "version": "1.0.0",
            "lockfileVersion": 2,
            "packages": {
                "": {
                    "name": "test-package",
                    "version": "1.0.0"
                },
                "node_modules/axios": {
                    "version": "1.0.0"
                },
                "node_modules/@types/node": {
                    "version": "18.0.0"
                }
            }
        }

        lockfile_path = tmp_path / "package-lock.json"
        lockfile_path.write_text(json.dumps(lockfile_content, indent=2))

        result = parse_package_lock(str(lockfile_path))

        assert "axios" in result
        assert "@types/node" in result
        assert len(result) == 2

    def test_parse_package_lock_missing_file(self, tmp_path):
        """Test parsing non-existent file returns empty list."""
        result = parse_package_lock(str(tmp_path / "nonexistent.json"))
        assert result == []

    def test_parse_package_lock_invalid_json(self, tmp_path):
        """Test parsing invalid JSON returns empty list."""
        lockfile_path = tmp_path / "package-lock.json"
        lockfile_path.write_text("invalid json {")

        result = parse_package_lock(str(lockfile_path))
        assert result == []

    def test_parse_package_lock_v1_non_dict_dependencies(self, tmp_path):
        """Test parsing v1 with non-dict dependencies (edge case)."""
        lockfile_content = {
            "name": "test-package",
            "version": "1.0.0",
            "lockfileVersion": 1,
            "dependencies": "not-a-dict"  # Invalid but should handle gracefully
        }

        lockfile_path = tmp_path / "package-lock.json"
        lockfile_path.write_text(json.dumps(lockfile_content, indent=2))

        result = parse_package_lock(str(lockfile_path))
        # Should return empty list or handle gracefully
        assert isinstance(result, list)

    def test_parse_package_lock_v2_with_dependencies_field(self, tmp_path):
        """Test parsing v2 with both packages and dependencies fields (backwards compatibility)."""
        lockfile_content = {
            "name": "test-package",
            "version": "1.0.0",
            "lockfileVersion": 2,
            "packages": {
                "": {"name": "test-package", "version": "1.0.0"},
                "node_modules/lodash": {"name": "lodash", "version": "4.17.21"}
            },
            "dependencies": {
                "express": {
                    "version": "4.18.2",
                    "dependencies": {
                        "body-parser": {
                            "version": "1.19.0"
                        }
                    }
                }
            }
        }

        lockfile_path = tmp_path / "package-lock.json"
        lockfile_path.write_text(json.dumps(lockfile_content, indent=2))

        result = parse_package_lock(str(lockfile_path))

        # Should include packages from both "packages" and "dependencies" fields
        assert "lodash" in result
        assert "express" in result
        assert "body-parser" in result
        assert len(result) >= 3

    def test_parse_package_lock_v2_dependencies_non_dict(self, tmp_path):
        """Test parsing v2 with non-dict dependencies field (edge case)."""
        lockfile_content = {
            "name": "test-package",
            "version": "1.0.0",
            "lockfileVersion": 2,
            "packages": {
                "": {"name": "test-package", "version": "1.0.0"},
                "node_modules/lodash": {"name": "lodash", "version": "4.17.21"}
            },
            "dependencies": "not-a-dict"  # Invalid but should handle gracefully
        }

        lockfile_path = tmp_path / "package-lock.json"
        lockfile_path.write_text(json.dumps(lockfile_content, indent=2))

        result = parse_package_lock(str(lockfile_path))
        # Should still extract from packages field
        assert "lodash" in result


class TestYarnLockParser:
    """Test yarn.lock parser."""

    def test_parse_yarn_lock_with_library(self, tmp_path, monkeypatch):
        """Test parsing yarn.lock using yarnlock library."""
        yarn_lock_content = """# This file is generated by running "yarn install" inside your project.
# Manual changes might be lost - proceed with caution!

__metadata:
  version: 4
  cacheKey: 7

"lodash@npm:^4.17.0":
  version: 4.17.21
  resolution: "lodash@npm:4.17.21"
  checksum: 10/abc123

"express@npm:^4.18.0":
  version: 4.18.2
  resolution: "express@npm:4.18.2"
  checksum: 10/def456
"""
        lockfile_path = tmp_path / "yarn.lock"
        lockfile_path.write_text(yarn_lock_content)

        # Mock yarnlock library
        mock_parsed = {
            "lodash@npm:^4.17.0": {"version": "4.17.21"},
            "express@npm:^4.18.0": {"version": "4.18.2"},
        }

        def mock_yarnlock_parse(content):
            return mock_parsed

        # Mock the import inside the function
        monkeypatch.setattr("yarnlock.yarnlock_parse", mock_yarnlock_parse)

        result = parse_yarn_lock(str(lockfile_path))

        assert "lodash" in result
        assert "express" in result
        assert len(result) == 2

    def test_parse_yarn_lock_custom_parser(self, tmp_path):
        """Test parsing yarn.lock with custom parser format (Yarn v1)."""
        # This test uses Yarn v1 format which should work with the custom parser
        # The yarnlock library may or may not handle this format, but our custom parser should
        yarn_lock_content = """# This file is generated by running "yarn install" inside your project.

lodash@^4.17.0:
  version "4.17.21"
  resolved "https://registry.yarnpkg.com/lodash/-/lodash-4.17.21.tgz#abc123"
  integrity sha512-abc123

express@^4.18.0:
  version "4.18.2"
  resolved "https://registry.yarnpkg.com/express/-/express-4.18.2.tgz#def456"
  integrity sha512-def456

"@types/node@^18.0.0":
  version "18.0.0"
  resolved "https://registry.yarnpkg.com/@types/node/-/node-18.0.0.tgz#xyz789"
  integrity sha512-xyz789
"""
        lockfile_path = tmp_path / "yarn.lock"
        lockfile_path.write_text(yarn_lock_content)

        # Test that parsing works (may use library or custom parser)
        result = parse_yarn_lock(str(lockfile_path))

        assert "lodash" in result
        assert "express" in result
        assert "@types/node" in result
        assert len(result) == 3

    def test_parse_yarn_lock_scoped_packages(self, tmp_path):
        """Test parsing scoped packages in yarn.lock."""
        yarn_lock_content = """# yarn.lock

"@types/node@^18.0.0":
  version "18.0.0"
  resolved "https://registry.yarnpkg.com/@types/node/-/node-18.0.0.tgz#xyz789"

"@scope/package@^1.0.0":
  version "1.0.0"
  resolved "https://registry.yarnpkg.com/@scope/package/-/package-1.0.0.tgz#abc123"
"""
        lockfile_path = tmp_path / "yarn.lock"
        lockfile_path.write_text(yarn_lock_content)

        result = parse_yarn_lock(str(lockfile_path))

        assert "@types/node" in result
        assert "@scope/package" in result
        assert len(result) == 2

    def test_parse_yarn_lock_missing_file(self, tmp_path):
        """Test parsing non-existent file returns empty list."""
        result = parse_yarn_lock(str(tmp_path / "nonexistent.lock"))
        assert result == []

    def test_parse_yarn_lock_with_empty_keys(self, tmp_path, monkeypatch):
        """Test parsing yarn.lock with empty or non-string keys (edge case)."""
        # Mock yarnlock library to return dict with empty/non-string keys
        mock_parsed = {
            "": {"version": "1.0.0"},  # Empty key
            123: {"version": "1.0.0"},  # Non-string key
            "lodash@npm:^4.17.0": {"version": "4.17.21"},  # Valid key
        }

        def mock_yarnlock_parse(content):
            return mock_parsed

        monkeypatch.setattr("yarnlock.yarnlock_parse", mock_yarnlock_parse)

        lockfile_path = tmp_path / "yarn.lock"
        lockfile_path.write_text("# yarn.lock\n")

        result = parse_yarn_lock(str(lockfile_path))

        # Should only include valid package names, skip empty/non-string keys
        assert "lodash" in result
        assert "" not in result
        assert len(result) == 1

    def test_parse_yarn_lock_custom_parser_path(self, tmp_path, monkeypatch):
        """Test that custom parser is used when yarnlock library raises ImportError."""
        yarn_lock_content = """# yarn.lock

lodash@^4.17.0:
  version "4.17.21"
  resolved "https://registry.yarnpkg.com/lodash/-/lodash-4.17.21.tgz#abc123"

express@^4.18.0:
  version "4.18.2"
  resolved "https://registry.yarnpkg.com/express/-/express-4.18.2.tgz#def456"
"""
        lockfile_path = tmp_path / "yarn.lock"
        lockfile_path.write_text(yarn_lock_content)

        # Mock ImportError when trying to import yarnlock
        original_import = __import__
        def mock_import(name, *args, **kwargs):
            if name == "yarnlock":
                raise ImportError("No module named 'yarnlock'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        result = parse_yarn_lock(str(lockfile_path))

        # Should use custom parser and extract packages
        assert "lodash" in result
        assert "express" in result
        assert len(result) == 2

    def test_parse_yarn_lock_custom_parser_non_scoped_package(self, tmp_path, monkeypatch):
        """Test custom parser handles non-scoped packages correctly."""
        yarn_lock_content = """# yarn.lock

lodash@^4.17.0:
  version "4.17.21"
  resolved "https://registry.yarnpkg.com/lodash/-/lodash-4.17.21.tgz#abc123"
"""
        lockfile_path = tmp_path / "yarn.lock"
        lockfile_path.write_text(yarn_lock_content)

        # Mock ImportError to force custom parser
        original_import = __import__
        def mock_import(name, *args, **kwargs):
            if name == "yarnlock":
                raise ImportError("No module named 'yarnlock'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        result = parse_yarn_lock(str(lockfile_path))

        # Should extract non-scoped package (line 202: else branch)
        assert "lodash" in result
        assert len(result) == 1

    def test_parse_yarn_lock_custom_parser_scoped_package(self, tmp_path, monkeypatch):
        """Test custom parser handles scoped packages correctly (covers line 199)."""
        # Yarn v1 format - scoped packages can be quoted or unquoted
        # Test with unquoted format which the regex should match
        yarn_lock_content = """# yarn.lock

@types/node@^18.0.0:
  version "18.0.0"
  resolved "https://registry.yarnpkg.com/@types/node/-/node-18.0.0.tgz#xyz789"
"""
        lockfile_path = tmp_path / "yarn.lock"
        lockfile_path.write_text(yarn_lock_content)

        # Mock ImportError to force custom parser (not library)
        original_import = __import__
        def mock_import(name, *args, **kwargs):
            if name == "yarnlock":
                raise ImportError("No module named 'yarnlock'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        result = parse_yarn_lock(str(lockfile_path))

        # Should extract scoped package (line 199: if branch for scoped packages)
        assert "@types/node" in result
        assert len(result) == 1

    def test_parse_yarn_lock_custom_parser_io_error(self, tmp_path, monkeypatch):
        """Test custom parser handles IOError gracefully."""
        # Mock ImportError to force custom parser path
        original_import = __import__
        def mock_import(name, *args, **kwargs):
            if name == "yarnlock":
                raise ImportError("No module named 'yarnlock'")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)

        # Use non-existent file to trigger IOError
        result = parse_yarn_lock(str(tmp_path / "nonexistent.lock"))
        assert result == []


class TestBunLockParser:
    """Test bun.lock parser."""

    def test_parse_bun_lock_basic(self, tmp_path):
        """Test parsing basic bun.lock file."""
        bun_lock_content = """{
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
        lockfile_path = tmp_path / "bun.lock"
        lockfile_path.write_text(bun_lock_content)

        result = parse_bun_lock(str(lockfile_path))

        assert "lodash" in result
        assert "express" in result
        assert len(result) == 2

    def test_parse_bun_lock_with_comments(self, tmp_path):
        """Test parsing bun.lock with JSONC comments."""
        bun_lock_content = """{
  // This is a comment
  "lockfileVersion": 6,
  "packages": {
    "": {
      "name": "test-package",
      "version": "1.0.0"
    },
    /* Another comment */
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
        lockfile_path = tmp_path / "bun.lock"
        lockfile_path.write_text(bun_lock_content)

        result = parse_bun_lock(str(lockfile_path))

        assert "lodash" in result
        assert "express" in result
        assert len(result) == 2

    def test_parse_bun_lock_with_trailing_commas(self, tmp_path):
        """Test parsing bun.lock with trailing commas (JSONC feature)."""
        bun_lock_content = """{
  "lockfileVersion": 6,
  "packages": {
    "": {
      "name": "test-package",
      "version": "1.0.0",
    },
    "node_modules/lodash": {
      "name": "lodash",
      "version": "4.17.21",
    },
  },
}
"""
        lockfile_path = tmp_path / "bun.lock"
        lockfile_path.write_text(bun_lock_content)

        result = parse_bun_lock(str(lockfile_path))

        assert "lodash" in result
        assert len(result) == 1

    def test_parse_bun_lock_scoped_packages(self, tmp_path):
        """Test parsing scoped packages in bun.lock."""
        bun_lock_content = """{
  "lockfileVersion": 6,
  "packages": {
    "": {
      "name": "test-package",
      "version": "1.0.0"
    },
    "node_modules/@types/node": {
      "name": "@types/node",
      "version": "18.0.0"
    },
    "node_modules/@scope/package": {
      "name": "@scope/package",
      "version": "1.0.0"
    }
  }
}
"""
        lockfile_path = tmp_path / "bun.lock"
        lockfile_path.write_text(bun_lock_content)

        result = parse_bun_lock(str(lockfile_path))

        assert "@types/node" in result
        assert "@scope/package" in result
        assert len(result) == 2

    def test_parse_bun_lock_with_dependencies_field(self, tmp_path):
        """Test parsing bun.lock with dependencies field."""
        bun_lock_content = """{
  "lockfileVersion": 6,
  "packages": {
    "": {
      "name": "test-package",
      "version": "1.0.0"
    },
    "node_modules/lodash": {
      "name": "lodash",
      "version": "4.17.21"
    }
  },
  "dependencies": {
    "lodash": {
      "version": "4.17.21",
      "dependencies": {
        "underscore": {
          "version": "1.13.0"
        }
      }
    }
  }
}
"""
        lockfile_path = tmp_path / "bun.lock"
        lockfile_path.write_text(bun_lock_content)

        result = parse_bun_lock(str(lockfile_path))

        assert "lodash" in result
        assert "underscore" in result
        assert len(result) == 2

    def test_parse_bun_lock_missing_file(self, tmp_path):
        """Test parsing non-existent file returns empty list."""
        result = parse_bun_lock(str(tmp_path / "nonexistent.lock"))
        assert result == []

    def test_parse_bun_lock_invalid_json(self, tmp_path):
        """Test parsing invalid JSON returns empty list."""
        lockfile_path = tmp_path / "bun.lock"
        lockfile_path.write_text("invalid json {")

        result = parse_bun_lock(str(lockfile_path))
        assert result == []

    def test_parse_bun_lock_non_dict_dependencies(self, tmp_path):
        """Test parsing bun.lock with non-dict dependencies field (edge case)."""
        bun_lock_content = """{
  "lockfileVersion": 6,
  "packages": {
    "": {
      "name": "test-package",
      "version": "1.0.0"
    },
    "node_modules/lodash": {
      "name": "lodash",
      "version": "4.17.21"
    }
  },
  "dependencies": "not-a-dict"
}
"""
        lockfile_path = tmp_path / "bun.lock"
        lockfile_path.write_text(bun_lock_content)

        result = parse_bun_lock(str(lockfile_path))

        # Should still extract from packages field
        assert "lodash" in result
        assert len(result) == 1

    def test_parse_bun_lock_packages_not_dict(self, tmp_path):
        """Test parsing bun.lock when packages field is not a dict."""
        bun_lock_content = """{
  "lockfileVersion": 6,
  "packages": "not-a-dict"
}
"""
        lockfile_path = tmp_path / "bun.lock"
        lockfile_path.write_text(bun_lock_content)

        result = parse_bun_lock(str(lockfile_path))
        # Should handle gracefully
        assert isinstance(result, list)


class TestJsoncCommentStripper:
    """Test JSONC comment stripping."""

    def test_strip_single_line_comments(self):
        """Test stripping single-line comments."""
        content = """{
  // This is a comment
  "key": "value"
}"""
        result = _strip_jsonc_comments(content)
        assert "//" not in result
        assert '"key"' in result

    def test_strip_multi_line_comments(self):
        """Test stripping multi-line comments."""
        content = """{
  /* This is a
     multi-line comment */
  "key": "value"
}"""
        result = _strip_jsonc_comments(content)
        assert "/*" not in result
        assert "*/" not in result
        assert '"key"' in result

    def test_strip_trailing_commas(self):
        """Test stripping trailing commas."""
        content = """{
  "key1": "value1",
  "key2": "value2",
}"""
        result = _strip_jsonc_comments(content)
        # Should be valid JSON after stripping
        json.loads(result)  # Should not raise

    def test_strip_mixed_comments_and_commas(self):
        """Test stripping both comments and trailing commas."""
        content = """{
  // Comment
  "key1": "value1",
  /* Another comment */
  "key2": "value2",
}"""
        result = _strip_jsonc_comments(content)
        json.loads(result)  # Should not raise
