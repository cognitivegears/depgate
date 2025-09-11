"""Maven discovery helpers split from the former monolithic registry/maven.py."""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any

from common.http_client import safe_get
from common.logging_utils import extra_context, is_debug_enabled
from repository.url_normalize import normalize_repo_url

logger = logging.getLogger(__name__)


def _resolve_latest_version(group: str, artifact: str) -> Optional[str]:
    """Resolve latest release version from Maven metadata.

    Args:
        group: Maven group ID
        artifact: Maven artifact ID

    Returns:
        Latest release version string or None if not found
    """
    # Convert group to path format
    group_path = group.replace(".", "/")
    metadata_url = f"https://repo1.maven.org/maven2/{group_path}/{artifact}/maven-metadata.xml"

    if is_debug_enabled(logger):
        logger.debug("Fetching Maven metadata", extra=extra_context(
            event="function_entry", component="discovery", action="resolve_latest_version",
            target="maven-metadata.xml", package_manager="maven"
        ))

    try:
        response = safe_get(metadata_url, context="maven")
        if response.status_code != 200:
            if is_debug_enabled(logger):
                logger.debug("Maven metadata fetch failed", extra=extra_context(
                    event="function_exit", component="discovery", action="resolve_latest_version",
                    outcome="fetch_failed", status_code=response.status_code, package_manager="maven"
                ))
            return None

        # Parse XML to find release version
        root = ET.fromstring(response.text)
        versioning = root.find("versioning")
        if versioning is not None:
            # Try release first, then latest
            release_elem = versioning.find("release")
            if release_elem is not None and release_elem.text:
                if is_debug_enabled(logger):
                    logger.debug("Found release version", extra=extra_context(
                        event="function_exit", component="discovery", action="resolve_latest_version",
                        outcome="found_release", package_manager="maven"
                    ))
                return release_elem.text

            latest_elem = versioning.find("latest")
            if latest_elem is not None and latest_elem.text:
                if is_debug_enabled(logger):
                    logger.debug("Found latest version", extra=extra_context(
                        event="function_exit", component="discovery", action="resolve_latest_version",
                        outcome="found_latest", package_manager="maven"
                    ))
                return latest_elem.text

    except (ET.ParseError, AttributeError):
        # Quietly ignore parse errors; caller will handle fallback behavior
        if is_debug_enabled(logger):
            logger.debug("Maven metadata parse error", extra=extra_context(
                event="anomaly", component="discovery", action="resolve_latest_version",
                outcome="parse_error", package_manager="maven"
            ))

    if is_debug_enabled(logger):
        logger.debug("No version found in Maven metadata", extra=extra_context(
            event="function_exit", component="discovery", action="resolve_latest_version",
            outcome="no_version", package_manager="maven"
        ))

    return None


def _artifact_pom_url(group: str, artifact: str, version: str) -> str:
    """Construct POM URL for given Maven coordinates.

    Args:
        group: Maven group ID
        artifact: Maven artifact ID
        version: Version string

    Returns:
        Full POM URL string
    """
    group_path = group.replace(".", "/")
    return f"https://repo1.maven.org/maven2/{group_path}/{artifact}/{version}/{artifact}-{version}.pom"


def _fetch_pom(group: str, artifact: str, version: str) -> Optional[str]:
    """Fetch POM content from Maven Central.

    Args:
        group: Maven group ID
        artifact: Maven artifact ID
        version: Version string

    Returns:
        POM XML content as string or None if fetch failed
    """
    pom_url = _artifact_pom_url(group, artifact, version)
    if is_debug_enabled(logger):
        logger.debug("Fetching POM file", extra=extra_context(
            event="function_entry", component="discovery", action="fetch_pom",
            target="pom.xml", package_manager="maven"
        ))

    try:
        response = safe_get(pom_url, context="maven")
        if response.status_code == 200:
            if is_debug_enabled(logger):
                logger.debug("POM fetch successful", extra=extra_context(
                    event="function_exit", component="discovery", action="fetch_pom",
                    outcome="success", package_manager="maven"
                ))
            return response.text
        if is_debug_enabled(logger):
            logger.debug("POM fetch failed", extra=extra_context(
                event="function_exit", component="discovery", action="fetch_pom",
                outcome="fetch_failed", status_code=response.status_code, package_manager="maven"
            ))
    except Exception:  # pylint: disable=broad-exception-caught
        # Ignore network exceptions; caller will handle absence
        if is_debug_enabled(logger):
            logger.debug("POM fetch exception", extra=extra_context(
                event="anomaly", component="discovery", action="fetch_pom",
                outcome="network_error", package_manager="maven"
            ))

    return None


def _parse_scm_from_pom(pom_xml: str) -> Dict[str, Any]:
    """Parse SCM information from POM XML.

    Args:
        pom_xml: POM XML content as string

    Returns:
        Dict containing SCM info and parent info
    """
    result: Dict[str, Any] = {
        "url": None,
        "connection": None,
        "developerConnection": None,
        "parent": None,
    }

    try:
        root = ET.fromstring(pom_xml)
        ns = ".//{http://maven.apache.org/POM/4.0.0}"

        # Parse SCM block
        scm_elem = root.find(f"{ns}scm")
        if scm_elem is not None:
            url_elem = scm_elem.find(f"{ns}url")
            if url_elem is not None:
                result["url"] = url_elem.text

            conn_elem = scm_elem.find(f"{ns}connection")
            if conn_elem is not None:
                result["connection"] = conn_elem.text

            dev_conn_elem = scm_elem.find(f"{ns}developerConnection")
            if dev_conn_elem is not None:
                result["developerConnection"] = dev_conn_elem.text

        # Parse parent block
        parent_elem = root.find(f"{ns}parent")
        if parent_elem is not None:
            parent_info: Dict[str, Any] = {}
            for field in ["groupId", "artifactId", "version"]:
                field_elem = parent_elem.find(f"{ns}{field}")
                if field_elem is not None:
                    parent_info[field] = field_elem.text
            if parent_info:
                result["parent"] = parent_info

    except (ET.ParseError, AttributeError):
        # Ignore parse errors; caller will handle absence
        pass

    return result

def _parse_license_from_pom(pom_xml: str) -> Dict[str, Any]:
    """Parse license information from POM XML.

    Args:
        pom_xml: POM XML content as string

    Returns:
        Dict with keys 'name' and 'url' when found (values may be None).
    """
    result: Dict[str, Any] = {"name": None, "url": None}
    try:
        root = ET.fromstring(pom_xml)
        ns = ".//{http://maven.apache.org/POM/4.0.0}"
        licenses_elem = root.find(f"{ns}licenses")
        if licenses_elem is not None:
            # Use the first license entry if multiple are present
            lic_elem = licenses_elem.find(f"{ns}license")
            if lic_elem is not None:
                name_elem = lic_elem.find(f"{ns}name")
                url_elem = lic_elem.find(f"{ns}url")

                if name_elem is not None and isinstance(name_elem.text, str):
                    val = name_elem.text.strip()
                    if val:
                        result["name"] = val

                if url_elem is not None and isinstance(url_elem.text, str):
                    val = url_elem.text.strip()
                    if val:
                        result["url"] = val
    except (ET.ParseError, AttributeError):
        # Ignore parse errors; caller will handle absence gracefully
        pass

    return result

def _normalize_scm_to_repo_url(scm: Dict[str, Any]) -> Optional[str]:
    """Normalize SCM connection strings to repository URL.

    Args:
        scm: SCM dictionary from _parse_scm_from_pom

    Returns:
        Normalized repository URL or None
    """

    # Try different SCM fields in priority order
    candidates = []
    if scm.get("url"):
        candidates.append(scm["url"])
    if scm.get("connection"):
        candidates.append(scm["connection"])
    if scm.get("developerConnection"):
        candidates.append(scm["developerConnection"])

    for candidate in candidates:
        normalized = normalize_repo_url(candidate)
        if normalized:
            return normalized.normalized_url

    return None


def _traverse_for_scm(  # pylint: disable=too-many-arguments, too-many-positional-arguments
    group: str,
    artifact: str,
    version: str,
    provenance: Dict[str, Any],
    depth: int = 0,
    max_depth: int = 8,
) -> Dict[str, Any]:
    """Traverse parent POM chain to find SCM information.

    Args:
        group: Current Maven group ID
        artifact: Current Maven artifact ID
        version: Current version
        provenance: Provenance tracking dictionary
        depth: Current traversal depth
        max_depth: Maximum traversal depth

    Returns:
        Dict with SCM information or empty dict if not found
    """
    if depth >= max_depth:
        return {}

    pom_xml = _fetch_pom(group, artifact, version)
    if not pom_xml:
        return {}

    scm_info = _parse_scm_from_pom(pom_xml)

    # Record provenance
    depth_key = f"depth{depth}" if depth > 0 else ""
    pom_url = _artifact_pom_url(group, artifact, version)
    provenance[f"maven_pom{depth_key}.url"] = pom_url

    # If we have SCM info, return it
    if scm_info.get("url") or scm_info.get("connection") or scm_info.get("developerConnection"):
        if depth > 0:
            provenance[f"maven_parent_pom.depth{depth}.scm.url"] = scm_info.get("url")
            provenance[f"maven_parent_pom.depth{depth}.scm.connection"] = scm_info.get("connection")
            provenance[
                f"maven_parent_pom.depth{depth}.scm.developerConnection"
            ] = scm_info.get("developerConnection")
        else:
            provenance["maven_pom.scm.url"] = scm_info.get("url")
            provenance["maven_pom.scm.connection"] = scm_info.get("connection")
            provenance["maven_pom.scm.developerConnection"] = scm_info.get("developerConnection")
        return scm_info

    # If no SCM but has parent, traverse up
    if scm_info.get("parent"):
        parent = scm_info["parent"]
        parent_group = parent.get("groupId")
        parent_artifact = parent.get("artifactId")
        parent_version = parent.get("version")

        if parent_group and parent_artifact and parent_version:
            return _traverse_for_scm(parent_group, parent_artifact, parent_version, provenance, depth + 1, max_depth)

    return {}


def _url_fallback_from_pom(pom_xml: str) -> Optional[str]:
    """Extract fallback repository URL from POM <url> field.

    Args:
        pom_xml: POM XML content

    Returns:
        Repository URL if found and looks like GitHub/GitLab, None otherwise
    """
    try:
        root = ET.fromstring(pom_xml)
        ns = ".//{http://maven.apache.org/POM/4.0.0}"

        url_elem = root.find(f"{ns}url")
        if url_elem is not None and url_elem.text:
            url = url_elem.text.strip()
            # Check if it looks like a GitHub/GitLab URL
            if "github.com" in url or "gitlab.com" in url:
                return url
    except (ET.ParseError, AttributeError):
        pass

    return None
