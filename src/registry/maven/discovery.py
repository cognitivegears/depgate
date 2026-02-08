"""Maven discovery helpers split from the former monolithic registry/maven.py."""
from __future__ import annotations

import logging
import threading
import xml.etree.ElementTree as ET
from typing import Optional, Dict, Any, List

from common.http_client import safe_get, safe_head
from common.logging_utils import extra_context, is_debug_enabled
from repository.url_normalize import normalize_repo_url

logger = logging.getLogger(__name__)

# Per-session cache for maven-metadata.xml content keyed by (group, artifact).
# Guarded by _metadata_cache_lock because the proxy may serve concurrent
# requests from a background thread.
_metadata_cache: Dict[str, ET.Element] = {}
_metadata_cache_lock = threading.Lock()


def _fetch_metadata_root(group: str, artifact: str) -> Optional[ET.Element]:
    """Fetch and cache parsed maven-metadata.xml for a group:artifact."""
    cache_key = f"{group}:{artifact}"
    with _metadata_cache_lock:
        if cache_key in _metadata_cache:
            return _metadata_cache[cache_key]

    group_path = group.replace(".", "/")
    metadata_url = f"https://repo1.maven.org/maven2/{group_path}/{artifact}/maven-metadata.xml"

    if is_debug_enabled(logger):
        logger.debug("Fetching Maven metadata", extra=extra_context(
            event="function_entry", component="discovery", action="fetch_metadata",
            target="maven-metadata.xml", package_manager="maven"
        ))

    try:
        response = safe_get(metadata_url, context="maven", fatal=False)
        if response.status_code != 200:
            if is_debug_enabled(logger):
                logger.debug("Maven metadata fetch failed", extra=extra_context(
                    event="function_exit", component="discovery", action="fetch_metadata",
                    outcome="fetch_failed", status_code=response.status_code, package_manager="maven"
                ))
            return None
        root = ET.fromstring(response.text)
        with _metadata_cache_lock:
            _metadata_cache[cache_key] = root
        return root
    except Exception:  # pylint: disable=broad-exception-caught
        if is_debug_enabled(logger):
            logger.debug("Maven metadata fetch/parse error", extra=extra_context(
                event="anomaly", component="discovery", action="fetch_metadata",
                outcome="error", package_manager="maven"
            ))
        return None


def _resolve_latest_version(group: str, artifact: str) -> Optional[str]:
    """Resolve latest release version from Maven metadata.

    Args:
        group: Maven group ID
        artifact: Maven artifact ID

    Returns:
        Latest release version string or None if not found
    """
    root = _fetch_metadata_root(group, artifact)
    if root is None:
        return None

    versioning = root.find("versioning")
    if versioning is not None:
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

    if is_debug_enabled(logger):
        logger.debug("No version found in Maven metadata", extra=extra_context(
            event="function_exit", component="discovery", action="resolve_latest_version",
            outcome="no_version", package_manager="maven"
        ))

    return None


def _metadata_versions(group: str, artifact: str) -> List[str]:
    """Return versions listed in maven-metadata.xml in source order."""
    root = _fetch_metadata_root(group, artifact)
    if root is None:
        return []
    try:
        versions_elem = root.find("versioning/versions")
        if versions_elem is None:
            return []
        versions = []
        for item in versions_elem.findall("version"):
            if item is not None and isinstance(item.text, str) and item.text.strip():
                versions.append(item.text.strip())
        return versions
    except Exception:  # pylint: disable=broad-exception-caught
        return []


def _previous_version(group: str, artifact: str, selected_version: str) -> Optional[str]:
    """Find previous published version from metadata list."""
    versions = _metadata_versions(group, artifact)
    if not versions:
        return None
    if selected_version in versions:
        idx = versions.index(selected_version)
        if idx > 0:
            return versions[idx - 1]
        return None
    if len(versions) >= 2:
        return versions[-2]
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


def _artifact_base_url(group: str, artifact: str, version: str) -> str:
    """Construct base artifact URL without extension."""
    group_path = group.replace(".", "/")
    return f"https://repo1.maven.org/maven2/{group_path}/{artifact}/{version}/{artifact}-{version}"


def _artifact_exists(url: str) -> bool:
    """Return True when Maven Central URL exists (HTTP 200).

    Uses HEAD to avoid downloading artifact content.
    """
    try:
        response = safe_head(url, context="maven", fatal=False)
        return response.status_code == 200
    except Exception:  # pylint: disable=broad-exception-caught
        return False


def _has_any_artifact_suffix(group: str, artifact: str, version: str, suffixes: List[str]) -> Optional[bool]:
    """Check whether any artifact path with suffix exists."""
    if not version:
        return None
    base = _artifact_base_url(group, artifact, version)
    checked = False
    for suffix in suffixes:
        checked = True
        if _artifact_exists(base + suffix):
            return True
    if not checked:
        return None
    return False


def _collect_trust_signals(group: str, artifact: str, version: str) -> Dict[str, Optional[bool]]:
    """Collect Maven supply-chain trust signals for a version."""
    signatures = _has_any_artifact_suffix(
        group,
        artifact,
        version,
        [".pom.asc", ".jar.asc"],
    )
    provenance = _has_any_artifact_suffix(
        group,
        artifact,
        version,
        [".pom.sigstore.json", ".jar.sigstore.json", ".pom.sigstore", ".jar.sigstore"],
    )
    checksums = _has_any_artifact_suffix(
        group,
        artifact,
        version,
        [
            ".pom.sha512",
            ".jar.sha512",
            ".pom.sha256",
            ".jar.sha256",
            ".pom.sha1",
            ".jar.sha1",
        ],
    )
    return {
        "registry_signature_present": signatures,
        "provenance_present": provenance,
        "checksums_present": checksums,
    }


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
        response = safe_get(pom_url, context="maven", fatal=False)
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
            # Check if it looks like a GitHub/GitLab URL by parsing it
            # (avoid substring matching in sanitized URLs)
            repo_ref = normalize_repo_url(url)
            if repo_ref is not None and repo_ref.host in ("github", "gitlab"):
                return url
    except (ET.ParseError, AttributeError):
        pass

    return None
