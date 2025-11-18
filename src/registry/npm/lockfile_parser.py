"""Lockfile parsers for npm ecosystem (package-lock.json, yarn.lock, bun.lock).

This module provides parsers to extract all dependencies (direct + transitive)
from various npm lockfile formats.
"""

from __future__ import annotations

import json
import logging
import re
from typing import List, Set


logger = logging.getLogger(__name__)


def _strip_jsonc_comments(content: str) -> str:
    """Strip comments from JSONC (JSON with comments) content.

    Removes:
    - Single-line comments (// ...)
    - Multi-line comments (/* ... */)
    - Trailing commas before closing brackets/braces

    Args:
        content: JSONC string content

    Returns:
        JSON string with comments removed
    """
    # Remove single-line comments
    content = re.sub(r'//.*?$', '', content, flags=re.MULTILINE)

    # Remove multi-line comments
    content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)

    # Remove trailing commas (simple approach - remove comma before } or ])
    content = re.sub(r',(\s*[}\]])', r'\1', content)

    return content


def parse_package_lock(lockfile_path: str) -> List[str]:
    """Extract all dependencies (direct + transitive) from package-lock.json.

    Supports lockfileVersion 1, 2, and 3.

    Args:
        lockfile_path: Path to package-lock.json file

    Returns:
        List of all unique package names (direct + transitive)
    """
    try:
        with open(lockfile_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        packages: Set[str] = set()
        lockfile_version = data.get("lockfileVersion", 1)

        if lockfile_version == 1:
            # Version 1: Nested dependencies structure
            def _extract_from_deps(deps: dict) -> None:
                """Recursively extract package names from nested dependencies."""
                if not isinstance(deps, dict):
                    return
                for pkg_name, pkg_info in deps.items():
                    if isinstance(pkg_info, dict):
                        packages.add(pkg_name)
                        # Recurse into nested dependencies
                        if "dependencies" in pkg_info:
                            _extract_from_deps(pkg_info["dependencies"])

            if "dependencies" in data:
                _extract_from_deps(data["dependencies"])

        elif lockfile_version in (2, 3):
            # Version 2/3: Flat packages structure
            if "packages" in data:
                for pkg_path, pkg_info in data["packages"].items():
                    # Skip root package (empty path)
                    if not pkg_path:
                        continue

                    if isinstance(pkg_info, dict):
                        # Prefer "name" field if present
                        if "name" in pkg_info:
                            packages.add(pkg_info["name"])
                        else:
                            # Extract package name from path (e.g., "node_modules/package-name" -> "package-name")
                            # Handle scoped packages (e.g., "node_modules/@scope/package-name" -> "@scope/package-name")
                            path_parts = pkg_path.split("/")
                            if path_parts:  # Defensive check for empty list
                                # Check if this is a scoped package (path ends with @scope/package-name)
                                if len(path_parts) >= 2 and path_parts[-2].startswith("@"):
                                    # Scoped package: "@scope/package-name"
                                    packages.add(f"{path_parts[-2]}/{path_parts[-1]}")
                                else:
                                    # Regular package: "package-name"
                                    packages.add(path_parts[-1])

            # Also check dependencies field if present (for backwards compatibility in v2)
            if "dependencies" in data:
                def _extract_from_deps_v2(deps: dict) -> None:
                    """Extract from v2 dependencies structure."""
                    if not isinstance(deps, dict):
                        return
                    for pkg_name, pkg_info in deps.items():
                        if isinstance(pkg_info, dict):
                            packages.add(pkg_name)
                            if "dependencies" in pkg_info:
                                _extract_from_deps_v2(pkg_info["dependencies"])

                _extract_from_deps_v2(data["dependencies"])

        return sorted(list(packages))

    except (FileNotFoundError, IOError, json.JSONDecodeError, KeyError) as e:
        logger.warning("Failed to parse package-lock.json: %s", e)
        return []


def parse_yarn_lock(lockfile_path: str, package_json_path: str | None = None) -> List[str]:
    """Extract all dependencies (direct + transitive) from yarn.lock.

    Uses the yarnlock library if available, falls back to custom parser.

    Args:
        lockfile_path: Path to yarn.lock file
        package_json_path: Optional path to package.json (for identifying direct deps)

    Returns:
        List of all unique package names (direct + transitive)
    """
    try:
        # Try using yarnlock library first
        try:
            from yarnlock import yarnlock_parse

            with open(lockfile_path, "r", encoding="utf-8") as f:
                content = f.read()

            parsed = yarnlock_parse(content)

            # Extract all package names from parsed structure
            packages: Set[str] = set()
            if isinstance(parsed, dict):
                for pkg_key, pkg_info in parsed.items():
                    # Skip empty keys
                    if not pkg_key or not isinstance(pkg_key, str):
                        continue
                    # pkg_key format: "package-name@version" or "@scope/package-name@version"
                    # Extract package name (handle scoped packages)
                    if "@" in pkg_key:
                        # Remove version part
                        pkg_name = pkg_key.rsplit("@", 1)[0]
                        if pkg_name:  # Only add non-empty names
                            packages.add(pkg_name)

            return sorted(list(packages))

        except ImportError:
            # Fallback to custom parser if yarnlock not available
            logger.debug("yarnlock library not available, using custom parser")
            return _parse_yarn_lock_custom(lockfile_path)

    except (FileNotFoundError, IOError, KeyError, Exception) as e:
        logger.warning("Failed to parse yarn.lock: %s", e)
        return []


def _parse_yarn_lock_custom(lockfile_path: str) -> List[str]:
    """Custom parser for yarn.lock (fallback when yarnlock library unavailable).

    Parses Yarn v1 format: package-name@version: version "x.y.z" resolved "url" ...

    Args:
        lockfile_path: Path to yarn.lock file

    Returns:
        List of all unique package names
    """
    try:
        with open(lockfile_path, "r", encoding="utf-8") as f:
            content = f.read()

        packages: Set[str] = set()

        # Pattern to match yarn.lock entries: "package-name@version:" or "@scope/package-name@version:"
        # Entry format: package-name@version:\n  version "x.y.z"\n  resolved "url"\n  ...
        pattern = r'^([^@\s"][^"\n]*?|@[^/]+/[^"\n]+?)@[^:\n]+:'

        for match in re.finditer(pattern, content, re.MULTILINE):
            pkg_key = match.group(1)
            # Extract package name (handle scoped packages like @scope/package)
            if pkg_key.startswith("@"):
                # Scoped package: @scope/package
                packages.add(pkg_key)
            else:
                # Regular package: package-name
                packages.add(pkg_key)

        return sorted(list(packages))

    except (FileNotFoundError, IOError) as e:
        logger.warning("Failed to parse yarn.lock with custom parser: %s", e)
        return []


def parse_bun_lock(lockfile_path: str) -> List[str]:
    """Extract all dependencies (direct + transitive) from bun.lock.

    bun.lock is JSONC format (JSON with comments). This function strips comments
    and parses as JSON.

    Args:
        lockfile_path: Path to bun.lock file

    Returns:
        List of all unique package names (direct + transitive)
    """
    try:
        with open(lockfile_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Strip JSONC comments
        json_content = _strip_jsonc_comments(content)

        # Parse as JSON
        data = json.loads(json_content)

        packages: Set[str] = set()

        # bun.lock structure is similar to package-lock.json v2/3
        # Check for "packages" field (flat structure)
        if "packages" in data and isinstance(data["packages"], dict):
            for pkg_path, pkg_info in data["packages"].items():
                # Skip root package (empty path)
                if not pkg_path:
                    continue

                if isinstance(pkg_info, dict):
                    # Prefer "name" field if present
                    if "name" in pkg_info:
                        packages.add(pkg_info["name"])
                    else:
                        # Extract package name from path (e.g., "node_modules/package-name" -> "package-name")
                        # Handle scoped packages (e.g., "node_modules/@scope/package-name" -> "@scope/package-name")
                        path_parts = pkg_path.split("/")
                        if path_parts:  # Defensive check
                            # Check if this is a scoped package (path ends with @scope/package-name)
                            if len(path_parts) >= 2 and path_parts[-2].startswith("@"):
                                # Scoped package: "@scope/package-name"
                                packages.add(f"{path_parts[-2]}/{path_parts[-1]}")
                            else:
                                # Regular package: "package-name"
                                packages.add(path_parts[-1])

        # Also check for "dependencies" field if present
        if "dependencies" in data:
            def _extract_from_deps(deps: dict) -> None:
                """Recursively extract package names from dependencies."""
                if not isinstance(deps, dict):
                    return
                for pkg_name, pkg_info in deps.items():
                    if isinstance(pkg_info, dict):
                        packages.add(pkg_name)
                        if "dependencies" in pkg_info:
                            _extract_from_deps(pkg_info["dependencies"])

            _extract_from_deps(data["dependencies"])

        return sorted(list(packages))

    except (FileNotFoundError, IOError, json.JSONDecodeError, KeyError) as e:
        logger.warning("Failed to parse bun.lock: %s", e)
        return []
