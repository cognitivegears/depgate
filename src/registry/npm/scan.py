"""NPM source scanner split from the former monolithic registry/npm.py."""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import List

from common.logging_utils import (
    log_discovered_files,
    log_selection,
    warn_multiple_lockfiles,
    warn_missing_expected,
    is_debug_enabled,
)

from constants import ExitCodes, Constants

logger = logging.getLogger(__name__)

# Import lockfile parsers at module level for better performance
from registry.npm.lockfile_parser import (
    parse_package_lock,
    parse_yarn_lock,
    parse_bun_lock,
)


def _discover_lockfiles(dir_path: str) -> dict[str, str | None]:
    """Discover lockfiles in a directory.

    Args:
        dir_path: Directory to search for lockfiles

    Returns:
        Dictionary with lockfile paths: {
            "package_lock": path or None,
            "yarn_lock": path or None,
            "bun_lock": path or None
        }
    """
    lockfiles = {
        "package_lock": None,
        "yarn_lock": None,
        "bun_lock": None,
    }

    package_lock_path = os.path.join(dir_path, Constants.PACKAGE_LOCK_FILE)
    yarn_lock_path = os.path.join(dir_path, Constants.YARN_LOCK_FILE)
    bun_lock_path = os.path.join(dir_path, Constants.BUN_LOCK_FILE)

    if os.path.isfile(package_lock_path):
        lockfiles["package_lock"] = package_lock_path
    if os.path.isfile(yarn_lock_path):
        lockfiles["yarn_lock"] = yarn_lock_path
    if os.path.isfile(bun_lock_path):
        lockfiles["bun_lock"] = bun_lock_path

    return lockfiles


def _select_lockfile(lockfiles: dict[str, str | None]) -> tuple[str | None, str]:
    """Select lockfile based on precedence: package-lock.json > yarn.lock > bun.lock.

    Args:
        lockfiles: Dictionary of discovered lockfiles

    Returns:
        Tuple of (selected_lockfile_path, rationale)
    """
    selected = None
    rationale = "no lockfile"
    alternatives = []

    if lockfiles["package_lock"]:
        selected = lockfiles["package_lock"]
        rationale = "preferring package-lock.json"
        if lockfiles["yarn_lock"]:
            alternatives.append(lockfiles["yarn_lock"])
        if lockfiles["bun_lock"]:
            alternatives.append(lockfiles["bun_lock"])
    elif lockfiles["yarn_lock"]:
        selected = lockfiles["yarn_lock"]
        rationale = "using yarn.lock"
        if lockfiles["bun_lock"]:
            alternatives.append(lockfiles["bun_lock"])
    elif lockfiles["bun_lock"]:
        selected = lockfiles["bun_lock"]
        rationale = "using bun.lock"

    if alternatives:
        warn_multiple_lockfiles(logger, "npm", selected, alternatives)

    return selected, rationale


def _parse_lockfile(lockfile_path: str) -> List[str]:
    """Parse a lockfile and extract all dependencies (direct + transitive).

    Args:
        lockfile_path: Path to the lockfile

    Returns:
        List of all unique package names
    """
    if lockfile_path.endswith(Constants.PACKAGE_LOCK_FILE):
        return parse_package_lock(lockfile_path)
    elif lockfile_path.endswith(Constants.YARN_LOCK_FILE):
        # For yarn.lock, we need package.json path for context
        dir_path = os.path.dirname(lockfile_path)
        package_json_path = os.path.join(dir_path, Constants.PACKAGE_JSON_FILE)
        return parse_yarn_lock(lockfile_path, package_json_path if os.path.isfile(package_json_path) else None)
    elif lockfile_path.endswith(Constants.BUN_LOCK_FILE):
        return parse_bun_lock(lockfile_path)
    else:
        logger.warning("Unknown lockfile format: %s", lockfile_path)
        return []


def _parse_package_json(package_json_path: str) -> List[str]:
    """Parse package.json and extract direct dependencies.

    Args:
        package_json_path: Path to package.json

    Returns:
        List of direct dependency names
    """
    try:
        with open(package_json_path, "r", encoding="utf-8") as file:
            body = file.read()
        filex = json.loads(body)
        deps = list(filex.get("dependencies", {}).keys())
        if "devDependencies" in filex:
            deps.extend(list(filex["devDependencies"].keys()))
        return deps
    except (FileNotFoundError, IOError, json.JSONDecodeError) as e:
        logger.warning("Failed to parse package.json: %s", e)
        return []


def scan_source(dir_name: str, recursive: bool = False, direct_only: bool = False, require_lockfile: bool = False) -> List[str]:
    """Scan the source code for dependencies.

    Discovers package.json and lockfiles (package-lock.json, yarn.lock, bun.lock).
    Uses lockfiles when available to extract all dependencies (direct + transitive).
    Falls back to package.json (direct only) if no lockfile or parsing fails.

    Precedence:
        1. package-lock.json
        2. yarn.lock
        3. bun.lock
        4. package.json (fallback)

    Args:
        dir_name: Directory to scan.
        recursive: Whether to scan recursively.
        direct_only: If True, only extract direct dependencies from package.json, even if lockfile exists.
        require_lockfile: If True, require a lockfile to be present (raises error if missing).

    Returns:
        List of dependencies found in the source code (all dependencies from lockfile,
        or direct dependencies from package.json).
    """
    try:
        logger.info("npm scanner engaged.")
        all_deps: List[str] = []

        if recursive:
            # Recursive scan: process each directory with package.json
            for root, _, files in os.walk(dir_name):
                if Constants.PACKAGE_JSON_FILE in files:
                    package_json_path = os.path.join(root, Constants.PACKAGE_JSON_FILE)

                    # Discover lockfiles in this directory
                    lockfiles = _discover_lockfiles(root)
                    discovered = {
                        "manifest": [package_json_path] if os.path.isfile(package_json_path) else [],
                        "lockfile": [lf for lf in lockfiles.values() if lf is not None],
                    }

                    if is_debug_enabled(logger):
                        log_discovered_files(logger, "npm", discovered)

                    # Select lockfile based on precedence
                    lockfile_path, rationale = _select_lockfile(lockfiles)

                    # Require lockfile validation
                    if require_lockfile and not lockfile_path:
                        expected_lockfiles = f"{Constants.PACKAGE_LOCK_FILE}, {Constants.YARN_LOCK_FILE}, or {Constants.BUN_LOCK_FILE}"
                        logger.error(
                            "Lockfile required but not found in '%s'. Expected one of: %s",
                            root,
                            expected_lockfiles,
                        )
                        sys.exit(ExitCodes.FILE_ERROR.value)

                    # Log selection
                    log_selection(logger, "npm", package_json_path, lockfile_path, rationale)

                    # Parse dependencies
                    if direct_only:
                        # Direct-only mode: use package.json even if lockfile exists
                        deps = _parse_package_json(package_json_path)
                        all_deps.extend(deps)
                    elif lockfile_path:
                        deps = _parse_lockfile(lockfile_path)
                        if deps:
                            all_deps.extend(deps)
                        else:
                            # Fallback to package.json if lockfile parsing failed
                            logger.debug("Lockfile parsing failed, falling back to package.json")
                            all_deps.extend(_parse_package_json(package_json_path))
                    else:
                        # No lockfile, use package.json
                        all_deps.extend(_parse_package_json(package_json_path))
        else:
            # Non-recursive scan: single directory
            package_json_path = os.path.join(dir_name, Constants.PACKAGE_JSON_FILE)

            if not os.path.isfile(package_json_path):
                logger.error("package.json not found, unable to continue.")
                sys.exit(ExitCodes.FILE_ERROR.value)

            # Discover lockfiles
            lockfiles = _discover_lockfiles(dir_name)
            discovered = {
                "manifest": [package_json_path],
                "lockfile": [lf for lf in lockfiles.values() if lf is not None],
            }

            if is_debug_enabled(logger):
                log_discovered_files(logger, "npm", discovered)

            # Select lockfile based on precedence
            lockfile_path, rationale = _select_lockfile(lockfiles)

            # Require lockfile validation
            if require_lockfile and not lockfile_path:
                expected_lockfiles = f"{Constants.PACKAGE_LOCK_FILE}, {Constants.YARN_LOCK_FILE}, or {Constants.BUN_LOCK_FILE}"
                logger.error(
                    "Lockfile required but not found in '%s'. Expected one of: %s",
                    dir_name,
                    expected_lockfiles,
                )
                sys.exit(ExitCodes.FILE_ERROR.value)

            # Log selection
            log_selection(logger, "npm", package_json_path, lockfile_path, rationale)

            # Parse dependencies
            if direct_only:
                # Direct-only mode: use package.json even if lockfile exists
                deps = _parse_package_json(package_json_path)
                all_deps.extend(deps)
            elif lockfile_path:
                deps = _parse_lockfile(lockfile_path)
                if deps:
                    all_deps.extend(deps)
                else:
                    # Fallback to package.json if lockfile parsing failed
                    logger.debug("Lockfile parsing failed, falling back to package.json")
                    all_deps.extend(_parse_package_json(package_json_path))
            else:
                # No lockfile, use package.json
                all_deps.extend(_parse_package_json(package_json_path))

        return sorted(list(set(all_deps)))

    except (FileNotFoundError, IOError, json.JSONDecodeError) as e:
        logger.error("Couldn't import from given path, error: %s", e)
        sys.exit(ExitCodes.FILE_ERROR.value)
