"""PyPI source scanner split from the former monolithic registry/pypi.py."""
from __future__ import annotations

import os
import sys
import logging
from typing import List

import requirements

from constants import ExitCodes, Constants


def scan_source(dir_name: str, recursive: bool = False) -> List[str]:
    """Scan the source directory for requirements.txt files.

    Args:
        dir_name: Directory to scan.
        recursive: Whether to recurse into subdirectories. Defaults to False.

    Returns:
        List of unique requirement names discovered.

    Exits:
        ExitCodes.FILE_ERROR when the top-level requirements.txt is missing in non-recursive mode,
        or when files cannot be read/parsed.
    """
    current_path = ""
    try:
        logging.info("PyPI scanner engaged.")
        req_files: List[str] = []
        if recursive:
            for root, _, files in os.walk(dir_name):
                if Constants.REQUIREMENTS_FILE in files:
                    req_files.append(os.path.join(root, Constants.REQUIREMENTS_FILE))
        else:
            current_path = os.path.join(dir_name, Constants.REQUIREMENTS_FILE)
            if os.path.isfile(current_path):
                req_files.append(current_path)
            else:
                logging.error("requirements.txt not found, unable to continue.")
                sys.exit(ExitCodes.FILE_ERROR.value)

        all_requirements: List[str] = []
        for req_path in req_files:
            with open(req_path, "r", encoding="utf-8") as file:
                body = file.read()
            reqs = requirements.parse(body)
            names = [getattr(x, "name", None) for x in list(reqs)]
            all_requirements.extend([n for n in names if isinstance(n, str) and n])
        return list(set(all_requirements))
    except (FileNotFoundError, IOError) as e:
        logging.error("Couldn't import from given path '%s', error: %s", current_path, e)
        sys.exit(ExitCodes.FILE_ERROR.value)
