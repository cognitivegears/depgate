"""NPM source scanner split from the former monolithic registry/npm.py."""

from __future__ import annotations

import json
import os
import sys
import logging
from typing import List

from constants import ExitCodes, Constants


def scan_source(dir_name: str, recursive: bool = False) -> List[str]:
    """Scan the source code for dependencies.

    Args:
        dir_name: Directory to scan.
        recursive: Whether to scan recursively.

    Returns:
        List of dependencies found in the source code.
    """
    try:
        logging.info("npm scanner engaged.")
        pkg_files: List[str] = []
        if recursive:
            for root, _, files in os.walk(dir_name):
                if Constants.PACKAGE_JSON_FILE in files:
                    pkg_files.append(os.path.join(root, Constants.PACKAGE_JSON_FILE))
        else:
            path = os.path.join(dir_name, Constants.PACKAGE_JSON_FILE)
            if os.path.isfile(path):
                pkg_files.append(path)
            else:
                logging.error("package.json not found, unable to continue.")
                sys.exit(ExitCodes.FILE_ERROR.value)

        lister: List[str] = []
        for pkg_path in pkg_files:
            with open(pkg_path, "r", encoding="utf-8") as file:
                body = file.read()
            filex = json.loads(body)
            lister.extend(list(filex.get("dependencies", {}).keys()))
            if "devDependencies" in filex:
                lister.extend(list(filex["devDependencies"].keys()))
        return list(set(lister))
    except (FileNotFoundError, IOError, json.JSONDecodeError) as e:
        logging.error("Couldn't import from given path, error: %s", e)
        sys.exit(ExitCodes.FILE_ERROR.value)
