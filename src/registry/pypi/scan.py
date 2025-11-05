"""PyPI source scanner split from the former monolithic registry/pypi.py."""
from __future__ import annotations

import os
import sys
import logging
from typing import List

from common.logging_utils import (
    log_discovered_files,
    log_selection,
    warn_multiple_lockfiles,
    warn_missing_expected,
    is_debug_enabled,
)

from constants import ExitCodes, Constants


def scan_source(dir_name: str, recursive: bool = False) -> List[str]:
    """Scan a directory for PyPI manifests and lockfiles, apply precedence rules,
    and return the set of direct dependency names.

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

    Missing manifests result in a WARN and graceful exit (no exception).

    Returns:
        List of unique direct dependency names.
    """
    logger = logging.getLogger(__name__)
    discovered = {"manifest": [], "lockfile": []}
    direct_names: List[str] = []

    try:
        logger.info("PyPI scanner engaged.")
        # Discover files
        for root, _, files in os.walk(dir_name):
            if Constants.PYPROJECT_TOML_FILE in files:
                discovered["manifest"].append(os.path.join(root, Constants.PYPROJECT_TOML_FILE))
            if Constants.REQUIREMENTS_FILE in files:
                discovered["manifest"].append(os.path.join(root, Constants.REQUIREMENTS_FILE))
            if Constants.UV_LOCK_FILE in files:
                discovered["lockfile"].append(os.path.join(root, Constants.UV_LOCK_FILE))
            if Constants.POETRY_LOCK_FILE in files:
                discovered["lockfile"].append(os.path.join(root, Constants.POETRY_LOCK_FILE))

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
            from versioning.parser import parse_pyproject_tools
            assert manifest_path is not None
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

        # Parse manifest to obtain direct dependencies
        from versioning.parser import parse_pyproject_for_direct_pypi, parse_requirements_txt
        direct_deps: dict = {}
        if manifest_path and manifest_path.endswith(Constants.PYPROJECT_TOML_FILE):
            direct_deps = parse_pyproject_for_direct_pypi(manifest_path)
        elif manifest_path and manifest_path.endswith(Constants.REQUIREMENTS_FILE):
            direct_deps = parse_requirements_txt(manifest_path)

        direct_names = list(direct_deps.keys())
        return direct_names

    except Exception as e:
        logger.error("Error during PyPI scan: %s", e)
        sys.exit(ExitCodes.FILE_ERROR.value)
