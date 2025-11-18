"""PyPI source scanner split from the former monolithic registry/pypi.py."""
from __future__ import annotations

import os
import sys
import logging
from typing import List, Dict, Optional

from common.logging_utils import (
    log_discovered_files,
    log_selection,
    warn_multiple_lockfiles,
    warn_missing_expected,
    is_debug_enabled,
)

from constants import ExitCodes, Constants
from registry.pypi.lockfile_parser import parse_uv_lock, parse_poetry_lock
from versioning.parser import (
    parse_pyproject_tools,
    parse_pyproject_for_direct_pypi,
    parse_requirements_txt,
)
from versioning.models import DependencyRecord


def _parse_dependencies_for_directory(
    manifest_path: str,
    lockfile_path: Optional[str],
    logger: logging.Logger,
) -> List[str]:
    """Parse dependencies from lockfile or manifest for a single directory.

    Args:
        manifest_path: Path to manifest file (pyproject.toml or requirements.txt)
        lockfile_path: Path to lockfile (uv.lock or poetry.lock), or None
        logger: Logger instance for debug messages

    Returns:
        List of dependency names (all from lockfile, or direct from manifest)
    """
    if lockfile_path:
        # Parse lockfile to get all dependencies (direct + transitive)
        if lockfile_path.endswith(Constants.UV_LOCK_FILE):
            deps = parse_uv_lock(lockfile_path)
        elif lockfile_path.endswith(Constants.POETRY_LOCK_FILE):
            deps = parse_poetry_lock(lockfile_path)
        else:
            deps = []

        if deps:
            return deps

        # Fallback to manifest if lockfile parsing failed
        logger.debug("Lockfile parsing failed, falling back to manifest")

    # No lockfile or lockfile parsing failed - use manifest (direct dependencies only)
    direct_deps: Dict[str, DependencyRecord] = {}
    if manifest_path.endswith(Constants.PYPROJECT_TOML_FILE):
        direct_deps = parse_pyproject_for_direct_pypi(manifest_path)
    elif manifest_path.endswith(Constants.REQUIREMENTS_FILE):
        direct_deps = parse_requirements_txt(manifest_path)

    return list(direct_deps.keys())


def scan_source(dir_name: str, recursive: bool = False) -> List[str]:
    """Scan a directory for PyPI manifests and lockfiles, apply precedence rules,
    and return the set of all dependency names (direct + transitive from lockfiles).

    The function discovers:
      - Manifests: pyproject.toml (authoritative) and requirements.txt (fallback)
      - Lockfiles: uv.lock, poetry.lock

    Precedence:
      * If pyproject.toml contains a [tool.uv] section → prefer uv.lock.
      * Else if pyproject.toml contains a [tool.poetry] section → prefer poetry.lock.
      * If both lockfiles exist without a tool section → prefer uv.lock and emit a warning.
      * If both pyproject.toml and requirements.txt exist → use pyproject.toml as the
        authoritative manifest (DEBUG‑log the selection). Use requirements.txt only when
        pyproject.toml is missing.
      * When lockfile is present: extracts all dependencies (direct + transitive) from lockfile.
      * When no lockfile: extracts direct dependencies only from manifest.

    Missing manifests result in a WARN and graceful exit (no exception).

    Returns:
        List of unique dependency names (all dependencies from lockfile, or direct from manifest).
    """
    logger = logging.getLogger(__name__)
    discovered = {"manifest": [], "lockfile": []}

    try:
        logger.info("PyPI scanner engaged.")
        all_deps: List[str] = []

        if recursive:
            # Recursive scan: process each directory separately
            for root, _, files in os.walk(dir_name):
                # Find manifest in this directory
                manifest_path: str | None = None
                lockfile_path: str | None = None
                lockfile_rationale: str | None = None

                pyproject_path = os.path.join(root, Constants.PYPROJECT_TOML_FILE)
                req_path = os.path.join(root, Constants.REQUIREMENTS_FILE)
                uv_lock_path = os.path.join(root, Constants.UV_LOCK_FILE)
                poetry_lock_path = os.path.join(root, Constants.POETRY_LOCK_FILE)

                # Discover files in this directory
                discovered = {
                    "manifest": [],
                    "lockfile": [],
                }

                if os.path.isfile(pyproject_path):
                    discovered["manifest"].append(pyproject_path)
                    manifest_path = pyproject_path
                elif os.path.isfile(req_path):
                    discovered["manifest"].append(req_path)
                    manifest_path = req_path

                if os.path.isfile(uv_lock_path):
                    discovered["lockfile"].append(uv_lock_path)
                if os.path.isfile(poetry_lock_path):
                    discovered["lockfile"].append(poetry_lock_path)

                if not manifest_path:
                    # Skip directories without manifests (consistent with recursive behavior)
                    continue

                # Log discovered files
                if is_debug_enabled(logger):
                    log_discovered_files(logger, "pypi", discovered)

                # Determine lockfile based on manifest
                if manifest_path.endswith(Constants.PYPROJECT_TOML_FILE):
                    tools = parse_pyproject_tools(manifest_path)
                    if tools.get("tool_uv") and os.path.isfile(uv_lock_path):
                        lockfile_path = uv_lock_path
                        lockfile_rationale = "pyproject.toml declares [tool.uv]; using uv.lock"
                    elif tools.get("tool_poetry") and os.path.isfile(poetry_lock_path):
                        lockfile_path = poetry_lock_path
                        lockfile_rationale = "pyproject.toml declares [tool.poetry]; using poetry.lock"
                    else:
                        # No tool section or no matching lockfile
                        if os.path.isfile(uv_lock_path):
                            lockfile_path = uv_lock_path
                            lockfile_rationale = "no tool section; preferring uv.lock"
                        elif os.path.isfile(poetry_lock_path):
                            lockfile_path = poetry_lock_path
                            lockfile_rationale = "no tool section; using poetry.lock"
                        if os.path.isfile(uv_lock_path) and os.path.isfile(poetry_lock_path):
                            warn_multiple_lockfiles(logger, "pypi", uv_lock_path, [poetry_lock_path])
                # For requirements.txt, no lockfile support

                # Log selection
                log_selection(logger, "pypi", manifest_path, lockfile_path, lockfile_rationale or "no lockfile")

                # Parse dependencies for this directory
                deps = _parse_dependencies_for_directory(manifest_path, lockfile_path, logger)
                all_deps.extend(deps)
        else:
            # Non-recursive scan: single directory
            # Discover files
            discovered = {"manifest": [], "lockfile": []}

            pyproject_path = os.path.join(dir_name, Constants.PYPROJECT_TOML_FILE)
            req_path = os.path.join(dir_name, Constants.REQUIREMENTS_FILE)
            uv_lock_path = os.path.join(dir_name, Constants.UV_LOCK_FILE)
            poetry_lock_path = os.path.join(dir_name, Constants.POETRY_LOCK_FILE)

            if os.path.isfile(pyproject_path):
                discovered["manifest"].append(pyproject_path)
            if os.path.isfile(req_path):
                discovered["manifest"].append(req_path)
            if os.path.isfile(uv_lock_path):
                discovered["lockfile"].append(uv_lock_path)
            if os.path.isfile(poetry_lock_path):
                discovered["lockfile"].append(poetry_lock_path)

            # Log discovered files
            if is_debug_enabled(logger):
                log_discovered_files(logger, "pypi", discovered)

            # Determine which manifest to use
            manifest_path: str | None = None
            lockfile_path: str | None = None
            lockfile_rationale: str | None = None

            pyproject_paths = [p for p in discovered["manifest"] if p.endswith(Constants.PYPROJECT_TOML_FILE)]
            req_paths = [p for p in discovered["manifest"] if p.endswith(Constants.REQUIREMENTS_FILE)]

            if pyproject_paths:
                manifest_path = pyproject_paths[0]
                tools = parse_pyproject_tools(manifest_path)
                if tools.get("tool_uv"):
                    uv_locks = [p for p in discovered["lockfile"] if p.endswith(Constants.UV_LOCK_FILE)]
                    if uv_locks:
                        lockfile_path = uv_locks[0]
                        lockfile_rationale = "pyproject.toml declares [tool.uv]; using uv.lock"
                    else:
                        warn_missing_expected(logger, "pypi", [Constants.UV_LOCK_FILE])
                elif tools.get("tool_poetry"):
                    poetry_locks = [p for p in discovered["lockfile"] if p.endswith(Constants.POETRY_LOCK_FILE)]
                    if poetry_locks:
                        lockfile_path = poetry_locks[0]
                        lockfile_rationale = "pyproject.toml declares [tool.poetry]; using poetry.lock"
                    else:
                        warn_missing_expected(logger, "pypi", [Constants.POETRY_LOCK_FILE])
                else:
                    uv_locks = [p for p in discovered["lockfile"] if p.endswith(Constants.UV_LOCK_FILE)]
                    poetry_locks = [p for p in discovered["lockfile"] if p.endswith(Constants.POETRY_LOCK_FILE)]
                    if uv_locks:
                        lockfile_path = uv_locks[0]
                        lockfile_rationale = "no tool section; preferring uv.lock"
                    elif poetry_locks:
                        lockfile_path = poetry_locks[0]
                        lockfile_rationale = "no tool section; using poetry.lock"
                    if uv_locks and poetry_locks:
                        warn_multiple_lockfiles(logger, "pypi", uv_locks[0], poetry_locks)

            elif req_paths:
                manifest_path = req_paths[0]
                lockfile_path = None
            else:
                warn_missing_expected(logger, "pypi", [Constants.PYPROJECT_TOML_FILE, Constants.REQUIREMENTS_FILE])
                sys.exit(ExitCodes.FILE_ERROR.value)

            # Log selection
            log_selection(logger, "pypi", manifest_path, lockfile_path, lockfile_rationale or "no lockfile")

            # Parse dependencies: prefer lockfile (all dependencies) over manifest (direct only)
            if manifest_path:
                deps = _parse_dependencies_for_directory(manifest_path, lockfile_path, logger)
                all_deps.extend(deps)

        return sorted(list(set(all_deps)))

    except Exception as e:
        logger.error("Error during PyPI scan: %s", e)
        sys.exit(ExitCodes.FILE_ERROR.value)
