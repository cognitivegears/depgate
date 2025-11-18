"""NuGet discovery helpers: extract repository URLs and license information from nuspec metadata."""

import logging
from typing import Any, Dict, List, Optional, Tuple

from common.logging_utils import extra_context, is_debug_enabled

logger = logging.getLogger(__name__)


def _extract_repo_candidates(metadata: Dict[str, Any]) -> List[str]:
    """Extract repository URL candidates from NuGet package metadata.

    Args:
        metadata: Normalized package metadata dictionary

    Returns:
        List of candidate repository URLs
    """
    if is_debug_enabled(logger):
        logger.debug("Extracting repository candidates", extra=extra_context(
            event="function_entry", component="discovery", action="extract_repo_candidates",
            package_manager="nuget"
        ))

    candidates: List[str] = []

    # Primary: repositoryUrl field
    repository_url = metadata.get("repositoryUrl")
    if repository_url:
        if isinstance(repository_url, str) and repository_url.strip():
            candidates.append(repository_url.strip())
            if is_debug_enabled(logger):
                logger.debug("Using repositoryUrl as primary candidate", extra=extra_context(
                    event="decision", component="discovery", action="extract_repo_candidates",
                    target="repositoryUrl", outcome="primary", package_manager="nuget"
                ))

    # Fallback: projectUrl
    if not candidates:
        project_url = metadata.get("projectUrl")
        if project_url:
            if isinstance(project_url, str) and project_url.strip():
                candidates.append(project_url.strip())
                if is_debug_enabled(logger):
                    logger.debug("Using projectUrl as fallback candidate", extra=extra_context(
                        event="decision", component="discovery", action="extract_repo_candidates",
                        target="projectUrl", outcome="fallback", package_manager="nuget"
                    ))

    if is_debug_enabled(logger):
        logger.debug("Extracted repository candidates", extra=extra_context(
            event="function_exit", component="discovery", action="extract_repo_candidates",
            count=len(candidates), package_manager="nuget"
        ))

    return candidates


def _extract_license_from_metadata(metadata: Dict[str, Any]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract license information from NuGet package metadata.

    Args:
        metadata: Normalized package metadata dictionary

    Returns:
        Tuple of (license_id, license_source, license_url)
    """
    license_id: Optional[str] = None
    license_source: Optional[str] = None
    license_url: Optional[str] = None

    # Try license field (can be string or expression)
    license_field = metadata.get("license")
    if license_field:
        if isinstance(license_field, str):
            license_id = license_field.strip()
            license_source = "nuget_license"
        elif isinstance(license_field, dict):
            license_id = license_field.get("type") or license_field.get("expression")
            if license_id:
                license_id = str(license_id).strip()
                license_source = "nuget_license"

    # Try licenseUrl field
    license_url_field = metadata.get("licenseUrl")
    if license_url_field:
        if isinstance(license_url_field, str) and license_url_field.strip():
            license_url = license_url_field.strip()
            if license_source is None:
                license_source = "nuget_licenseUrl"

    return license_id, license_source, license_url

