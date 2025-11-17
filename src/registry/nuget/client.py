"""NuGet registry client: fetch package info via V3 API (primary) and V2 API (fallback)."""
from __future__ import annotations

import json
import sys
import time
import logging
import urllib.parse
from datetime import datetime as dt
from typing import Any, Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET

from constants import ExitCodes, Constants
from common.logging_utils import extra_context, is_debug_enabled, Timer, safe_url

import registry.nuget as nuget_pkg
from .enrich import _enrich_with_repo

logger = logging.getLogger(__name__)

# Shared HTTP JSON headers and timestamp format for this module
HEADERS_JSON = {"Accept": "application/json", "Content-Type": "application/json"}
TIME_FORMAT_ISO = "%Y-%m-%dT%H:%M:%S.%fZ"


def _log_http_pre(url: str) -> None:
    """Debug-log outbound HTTP request for NuGet client."""
    logger.debug(
        "HTTP request",
        extra=extra_context(
            event="http_request",
            component="client",
            action="GET",
            target=safe_url(url),
            package_manager="nuget",
        ),
    )


def _fetch_v3_service_index() -> Optional[Dict[str, Any]]:
    """Fetch and parse NuGet V3 service index.

    Returns:
        Service index dictionary or None if unavailable
    """
    try:
        url = Constants.REGISTRY_URL_NUGET_V3
        _log_http_pre(url)
        res = nuget_pkg.safe_get(url, context="nuget", headers=HEADERS_JSON)
        if res.status_code == 200:
            return json.loads(res.text)
    except Exception:
        pass
    return None


def _get_v3_registration_url(package_id: str, service_index: Dict[str, Any]) -> Optional[str]:
    """Get registration URL from service index.

    Args:
        package_id: Package identifier
        service_index: Service index dictionary

    Returns:
        Registration base URL or None
    """
    resources = service_index.get("resources", [])
    for resource in resources:
        if resource.get("@type") == "RegistrationsBaseUrl/3.6.0":
            base_url = resource.get("@id")
            if base_url:
                encoded_id = urllib.parse.quote(package_id.lower(), safe="")
                return f"{base_url}{encoded_id}/index.json"
    return None


def _fetch_v3_package_metadata(package_id: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Fetch package metadata from NuGet V3 API.

    Args:
        package_id: Package identifier

    Returns:
        Tuple of (package_metadata_dict, api_version_used)
    """
    service_index = _fetch_v3_service_index()
    if not service_index:
        return None, "v2"

    registration_url = _get_v3_registration_url(package_id, service_index)
    if not registration_url:
        return None, "v2"

    try:
        _log_http_pre(registration_url)
        res = nuget_pkg.safe_get(registration_url, context="nuget", headers=HEADERS_JSON)
        if res.status_code == 200:
            reg_data = json.loads(res.text)
            # Extract package metadata from registration pages
            metadata = {
                "id": package_id,
                "versions": [],
                "latest_version": None,
                "published": None,
                "projectUrl": None,
                "repositoryUrl": None,
                "licenseUrl": None,
                "license": None,
            }

            items = reg_data.get("items", [])
            all_versions = []
            latest_entry = None
            latest_date = None

            for item in items:
                items_in_page = item.get("items", [])
                for page_item in items_in_page:
                    catalog_entry = page_item.get("catalogEntry", {})
                    version = catalog_entry.get("version")
                    if version:
                        all_versions.append(version)
                        # Track latest by published date
                        published = catalog_entry.get("published")
                        if published:
                            try:
                                pub_date = dt.fromisoformat(published.replace("Z", "+00:00"))
                                if latest_date is None or pub_date > latest_date:
                                    latest_date = pub_date
                                    latest_entry = catalog_entry
                            except Exception:
                                pass

            metadata["versions"] = all_versions
            if latest_entry:
                metadata["latest_version"] = latest_entry.get("version")
                metadata["published"] = latest_entry.get("published")
                metadata["projectUrl"] = latest_entry.get("projectUrl")
                # Repository URL can be in repository field
                repo = latest_entry.get("repository")
                if isinstance(repo, str):
                    metadata["repositoryUrl"] = repo
                elif isinstance(repo, dict):
                    metadata["repositoryUrl"] = repo.get("url")
                metadata["licenseUrl"] = latest_entry.get("licenseUrl")
                # License can be a string or object
                license_field = latest_entry.get("license")
                if isinstance(license_field, str):
                    metadata["license"] = license_field
                elif isinstance(license_field, dict):
                    metadata["license"] = license_field.get("type") or license_field.get("expression")

            return metadata, "v3"
    except Exception:
        pass

    return None, "v2"


def _fetch_v2_package_metadata(package_id: str) -> Optional[Dict[str, Any]]:
    """Fetch package metadata from NuGet V2 API (OData).

    Args:
        package_id: Package identifier

    Returns:
        Package metadata dictionary or None
    """
    try:
        base_url = Constants.REGISTRY_URL_NUGET_V2
        # Query for latest version
        query = f"Packages()?$filter=Id eq '{package_id}'&$orderby=Version desc&$top=1"
        url = f"{base_url}{query}"
        _log_http_pre(url)

        # Try JSON first
        headers = {"Accept": "application/json"}
        res = nuget_pkg.safe_get(url, context="nuget", headers=headers)
        if res.status_code == 200:
            data = json.loads(res.text)
            # OData JSON format: {"d": {"results": [...]}}
            results = data.get("d", {}).get("results", [])
            if not results:
                results = data.get("results", [])

            if results:
                pkg = results[0]
                metadata = {
                    "id": pkg.get("Id", package_id),
                    "versions": [pkg.get("Version")] if pkg.get("Version") else [],
                    "latest_version": pkg.get("Version"),
                    "published": pkg.get("Published"),
                    "projectUrl": pkg.get("ProjectUrl"),
                    "repositoryUrl": None,  # V2 may not have this field
                    "licenseUrl": pkg.get("LicenseUrl"),
                    "license": None,  # V2 may not have license field
                }
                return metadata

        # Fallback: try XML format
        headers = {"Accept": "application/atom+xml,application/xml"}
        res = nuget_pkg.safe_get(url, context="nuget", headers=headers)
        if res.status_code == 200:
            root = ET.fromstring(res.text)
            # Parse OData XML (simplified - full parsing would be more robust)
            entries = root.findall(".//{http://www.w3.org/2005/Atom}entry")
            if entries:
                entry = entries[0]
                metadata = {
                    "id": package_id,
                    "versions": [],
                    "latest_version": None,
                    "published": None,
                    "projectUrl": None,
                    "repositoryUrl": None,
                    "licenseUrl": None,
                    "license": None,
                }
                # Extract properties from entry
                props = entry.find(".//{http://schemas.microsoft.com/ado/2007/08/dataservices}properties")
                if props is not None:
                    version_elem = props.find("{http://schemas.microsoft.com/ado/2007/08/dataservices}Version")
                    if version_elem is not None and version_elem.text:
                        metadata["latest_version"] = version_elem.text
                        metadata["versions"] = [version_elem.text]
                    published_elem = props.find("{http://schemas.microsoft.com/ado/2007/08/dataservices}Published")
                    if published_elem is not None and published_elem.text:
                        metadata["published"] = published_elem.text
                    project_url_elem = props.find("{http://schemas.microsoft.com/ado/2007/08/dataservices}ProjectUrl")
                    if project_url_elem is not None and project_url_elem.text:
                        metadata["projectUrl"] = project_url_elem.text
                    license_url_elem = props.find("{http://schemas.microsoft.com/ado/2007/08/dataservices}LicenseUrl")
                    if license_url_elem is not None and license_url_elem.text:
                        metadata["licenseUrl"] = license_url_elem.text
                return metadata
    except Exception:
        pass

    return None


def _normalize_metadata(metadata: Dict[str, Any], api_version: str) -> Dict[str, Any]:
    """Normalize metadata from V2 or V3 to common format.

    Args:
        metadata: Raw metadata dictionary
        api_version: "v3" or "v2"

    Returns:
        Normalized metadata dictionary
    """
    normalized = {
        "id": metadata.get("id", ""),
        "versions": metadata.get("versions", []),
        "latest_version": metadata.get("latest_version"),
        "published": metadata.get("published"),
        "projectUrl": metadata.get("projectUrl"),
        "repositoryUrl": metadata.get("repositoryUrl"),
        "licenseUrl": metadata.get("licenseUrl"),
        "license": metadata.get("license"),
        "api_version": api_version,
    }
    return normalized


def recv_pkg_info(pkgs, url: Optional[str] = None) -> None:
    """Check the existence of packages in the NuGet registry.

    Args:
        pkgs: List of MetaPackage instances to check
        url: Optional registry URL (not used, kept for API compatibility)
    """
    logging.info("NuGet registry engaged.")
    for pkg in pkgs:
        # Sleep to avoid rate limiting
        time.sleep(0.1)

        package_id = getattr(pkg, "pkg_name", "")
        if not package_id:
            pkg.exists = False
            continue

        # Try V3 first (primary)
        metadata, api_version = _fetch_v3_package_metadata(package_id)
        if not metadata:
            # Fallback to V2
            metadata = _fetch_v2_package_metadata(package_id)
            api_version = "v2"

        if not metadata:
            logger.warning(
                "Package not found in NuGet registry",
                extra=extra_context(
                    event="http_response",
                    outcome="not_found",
                    target=package_id,
                    package_manager="nuget",
                ),
            )
            pkg.exists = False
            continue

        # Normalize metadata
        normalized = _normalize_metadata(metadata, api_version)

        # Log which API version was used
        if is_debug_enabled(logger):
            logger.debug(
                "NuGet package metadata fetched",
                extra=extra_context(
                    event="package_found",
                    component="client",
                    action="fetch_metadata",
                    outcome="success",
                    api_version=api_version,
                    package_manager="nuget",
                    target=package_id,
                ),
            )

        pkg.exists = True
        pkg.version_count = len(normalized.get("versions", []))

        # Extract timestamp
        published = normalized.get("published")
        if published:
            try:
                # Try ISO format
                pub_date = dt.fromisoformat(published.replace("Z", "+00:00"))
                pkg.timestamp = int(pub_date.timestamp() * 1000)
            except Exception:
                try:
                    # Try parsing as string
                    pub_date = dt.strptime(published, TIME_FORMAT_ISO)
                    pkg.timestamp = int(pub_date.timestamp() * 1000)
                except Exception:
                    pkg.timestamp = 0
        else:
            pkg.timestamp = 0

        # Store metadata for enrichment
        pkg._nuget_metadata = normalized  # type: ignore[attr-defined]

        # Enrich with repository discovery and validation
        _enrich_with_repo(pkg, normalized)
