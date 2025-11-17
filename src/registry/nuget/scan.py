"""NuGet source scanner: scan for .csproj, packages.config, project.json, and Directory.Build.props files."""
from __future__ import annotations

import json
import logging
import os
import sys
import xml.etree.ElementTree as ET
from typing import List
from glob import glob

from constants import ExitCodes, Constants
from common.logging_utils import (
    log_discovered_files,
    log_selection,
    is_debug_enabled,
)

logger = logging.getLogger(__name__)


def _scan_csproj_files(dir_name: str, recursive: bool) -> List[str]:
    """Scan .csproj files for PackageReference elements.

    Args:
        dir_name: Directory to scan
        recursive: Whether to scan recursively

    Returns:
        List of package identifiers
    """
    packages: List[str] = []
    pattern = "**/*.csproj" if recursive else "*.csproj"
    csproj_files = glob(os.path.join(dir_name, pattern), recursive=recursive)

    for csproj_path in csproj_files:
        try:
            tree = ET.parse(csproj_path)
            root = tree.getroot()
            # Remove namespace for easier parsing
            for elem in root.iter():
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}')[1]

            # Find PackageReference elements
            for package_ref in root.findall(".//PackageReference"):
                include_attr = package_ref.get("Include")
                if include_attr:
                    packages.append(include_attr)
        except (ET.ParseError, IOError) as e:
            logger.warning("Couldn't parse .csproj file %s: %s", csproj_path, e)
            continue

    return packages


def _scan_packages_config(dir_name: str, recursive: bool) -> List[str]:
    """Scan packages.config files for package elements.

    Args:
        dir_name: Directory to scan
        recursive: Whether to scan recursively

    Returns:
        List of package identifiers
    """
    packages: List[str] = []
    pattern = "**/packages.config" if recursive else "packages.config"
    config_files = glob(os.path.join(dir_name, pattern), recursive=recursive)

    for config_path in config_files:
        try:
            tree = ET.parse(config_path)
            root = tree.getroot()
            # Remove namespace
            for elem in root.iter():
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}')[1]

            for package in root.findall(".//package"):
                id_attr = package.get("id")
                if id_attr:
                    packages.append(id_attr)
        except (ET.ParseError, IOError) as e:
            logger.warning("Couldn't parse packages.config file %s: %s", config_path, e)
            continue

    return packages


def _scan_project_json(dir_name: str, recursive: bool) -> List[str]:
    """Scan project.json files for dependencies.

    Args:
        dir_name: Directory to scan
        recursive: Whether to scan recursively

    Returns:
        List of package identifiers
    """
    packages: List[str] = []
    pattern = "**/project.json" if recursive else "project.json"
    json_files = glob(os.path.join(dir_name, pattern), recursive=recursive)

    for json_path in json_files:
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                dependencies = data.get("dependencies", {})
                if isinstance(dependencies, dict):
                    packages.extend(dependencies.keys())
        except (IOError, json.JSONDecodeError, KeyError) as e:
            logger.warning("Couldn't parse project.json file %s: %s", json_path, e)
            continue

    return packages


def _scan_directory_build_props(dir_name: str, recursive: bool) -> List[str]:
    """Scan Directory.Build.props files for PackageReference elements.

    Args:
        dir_name: Directory to scan
        recursive: Whether to scan recursively

    Returns:
        List of package identifiers
    """
    packages: List[str] = []
    pattern = "**/Directory.Build.props" if recursive else "Directory.Build.props"
    props_files = glob(os.path.join(dir_name, pattern), recursive=recursive)

    for props_path in props_files:
        try:
            tree = ET.parse(props_path)
            root = tree.getroot()
            # Remove namespace
            for elem in root.iter():
                if '}' in elem.tag:
                    elem.tag = elem.tag.split('}')[1]

            # Find PackageReference elements
            for package_ref in root.findall(".//PackageReference"):
                include_attr = package_ref.get("Include")
                if include_attr:
                    packages.append(include_attr)
        except (ET.ParseError, IOError) as e:
            logger.warning("Couldn't parse Directory.Build.props file %s: %s", props_path, e)
            continue

    return packages


def scan_source(dir_name: str, recursive: bool = False) -> List[str]:
    """Scan the source code for NuGet dependencies.

    Args:
        dir_name: Directory to scan.
        recursive: Whether to scan recursively.

    Returns:
        List of package identifiers found in the source code.
    """
    try:
        logging.info("NuGet scanner engaged.")
        all_packages: List[str] = []

        if recursive:
            if is_debug_enabled(logger):
                discovered = {"manifest": [], "lockfile": []}
                log_discovered_files(logger, "nuget", discovered)

        # Scan .csproj files
        csproj_packages = _scan_csproj_files(dir_name, recursive)
        all_packages.extend(csproj_packages)

        # Scan packages.config files
        config_packages = _scan_packages_config(dir_name, recursive)
        all_packages.extend(config_packages)

        # Scan project.json files
        json_packages = _scan_project_json(dir_name, recursive)
        all_packages.extend(json_packages)

        # Scan Directory.Build.props files
        props_packages = _scan_directory_build_props(dir_name, recursive)
        all_packages.extend(props_packages)

        if not all_packages and not recursive:
            # Check if any NuGet files exist
            csproj_path = os.path.join(dir_name, "*.csproj")
            config_path = os.path.join(dir_name, Constants.PACKAGES_CONFIG_FILE)
            json_path = os.path.join(dir_name, Constants.PROJECT_JSON_FILE)
            props_path = os.path.join(dir_name, "Directory.Build.props")

            has_files = (
                bool(glob(csproj_path)) or
                os.path.isfile(config_path) or
                os.path.isfile(json_path) or
                os.path.isfile(props_path)
            )

            if not has_files:
                logging.error("No NuGet project files found (.csproj, packages.config, project.json, or Directory.Build.props). Unable to scan.")
                sys.exit(ExitCodes.FILE_ERROR.value)

        return list(set(all_packages))
    except (FileNotFoundError, IOError, json.JSONDecodeError, ET.ParseError) as e:
        logging.error("Couldn't import from given path, error: %s", e)
        sys.exit(ExitCodes.FILE_ERROR.value)
