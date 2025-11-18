"""Lockfile parsers for PyPI ecosystem (uv.lock, poetry.lock).

This module provides parsers to extract all dependencies (direct + transitive)
from various Python lockfile formats.
"""

from __future__ import annotations

import logging
from typing import List, Set

logger = logging.getLogger(__name__)


def parse_uv_lock(lockfile_path: str) -> List[str]:
    """Extract all dependencies (direct + transitive) from uv.lock.

    uv.lock is a TOML file with [[package]] sections. Each package has a "name" field.
    All packages in the lockfile are included (direct + transitive).

    Args:
        lockfile_path: Path to uv.lock file

    Returns:
        List of all unique package names (direct + transitive)
    """
    try:
        try:
            import tomllib as toml  # type: ignore
        except Exception:  # pylint: disable=broad-exception-caught
            import tomli as toml  # type: ignore

        with open(lockfile_path, "rb") as f:
            data = toml.load(f) or {}

        packages: Set[str] = set()

        # uv.lock has [[package]] sections (array of tables in TOML)
        package_list = data.get("package", [])
        if isinstance(package_list, list):
            for pkg in package_list:
                if isinstance(pkg, dict) and "name" in pkg:
                    packages.add(pkg["name"])

        return sorted(list(packages))

    except FileNotFoundError as e:
        logger.warning("uv.lock file not found: %s", e)
        return []
    except IOError as e:
        logger.warning("Failed to read uv.lock file: %s", e)
        return []
    except (KeyError, ValueError, TypeError) as e:
        logger.warning("Failed to parse uv.lock (invalid format): %s", e)
        return []
    except Exception as e:
        logger.warning("Unexpected error parsing uv.lock: %s (type: %s)", e, type(e).__name__)
        return []


def parse_poetry_lock(lockfile_path: str) -> List[str]:
    """Extract all dependencies (direct + transitive) from poetry.lock.

    poetry.lock is a TOML file with [[package]] sections. Each package has a "name" field.
    All packages in the lockfile are included (direct + transitive).

    Args:
        lockfile_path: Path to poetry.lock file

    Returns:
        List of all unique package names (direct + transitive)
    """
    try:
        try:
            import tomllib as toml  # type: ignore
        except Exception:  # pylint: disable=broad-exception-caught
            import tomli as toml  # type: ignore

        with open(lockfile_path, "rb") as f:
            data = toml.load(f) or {}

        packages: Set[str] = set()

        # poetry.lock has [[package]] sections (array of tables in TOML)
        package_list = data.get("package", [])
        if isinstance(package_list, list):
            for pkg in package_list:
                if isinstance(pkg, dict) and "name" in pkg:
                    packages.add(pkg["name"])

        return sorted(list(packages))

    except FileNotFoundError as e:
        logger.warning("poetry.lock file not found: %s", e)
        return []
    except IOError as e:
        logger.warning("Failed to read poetry.lock file: %s", e)
        return []
    except (KeyError, ValueError, TypeError) as e:
        logger.warning("Failed to parse poetry.lock (invalid format): %s", e)
        return []
    except Exception as e:
        logger.warning("Unexpected error parsing poetry.lock: %s (type: %s)", e, type(e).__name__)
        return []
