"""NPM discovery helpers split from the former monolithic registry/npm.py."""

import logging
from typing import Any, Dict, List, Tuple, Optional

from common.logging_utils import extra_context, is_debug_enabled

logger = logging.getLogger(__name__)


def get_keys(data: Dict[str, Any]) -> List[str]:
    """Get all keys from a nested dictionary.

    Args:
        data: Dictionary to extract keys from.

    Returns:
        List of all keys in the dictionary.
    """
    result: List[str] = []
    for key in data.keys():
        if not isinstance(data[key], dict):
            result.append(key)
        else:
            result += get_keys(data[key])  # type: ignore[arg-type]
    return result


def _extract_latest_version(packument: Dict[str, Any]) -> str:
    """Extract latest version from packument dist-tags.

    Args:
        packument: NPM packument dictionary

    Returns:
        Latest version string or empty string if not found
    """
    dist_tags = packument.get("dist-tags", {})
    return dist_tags.get("latest", "")


def _parse_repository_field(version_info: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Parse repository field from version info, handling string or object formats.

    Args:
        version_info: Version dictionary from packument

    Returns:
        Tuple of (candidate_url, directory) where directory may be None
    """
    if is_debug_enabled(logger):
        logger.debug("Parsing repository field", extra=extra_context(
            event="function_entry", component="discovery", action="parse_repository_field",
            package_manager="npm"
        ))
    repo = version_info.get("repository")
    if not repo:
        if is_debug_enabled(logger):
            logger.debug("No repository field found in version info", extra=extra_context(
                event="decision", component="discovery", action="parse_repository_field",
                target="repository", outcome="none", package_manager="npm"
            ))
            logger.debug("Finished parsing repository field", extra=extra_context(
                event="function_exit", component="discovery", action="parse_repository_field",
                outcome="none", package_manager="npm"
            ))
        return None, None

    if isinstance(repo, str):
        if is_debug_enabled(logger):
            logger.debug("Repository field is string format", extra=extra_context(
                event="decision", component="discovery", action="parse_repository_field",
                target="repository", outcome="string_format", package_manager="npm"
            ))
            logger.debug("Finished parsing repository field", extra=extra_context(
                event="function_exit", component="discovery", action="parse_repository_field",
                outcome="string", package_manager="npm"
            ))
        return repo, None
    if isinstance(repo, dict):
        url = repo.get("url")
        directory = repo.get("directory")
        if is_debug_enabled(logger):
            logger.debug("Repository field is object format", extra=extra_context(
                event="decision", component="discovery", action="parse_repository_field",
                target="repository", outcome="object_format", package_manager="npm"
            ))
        if not url:
            logger.warning("Repository object missing url; ignoring", extra=extra_context(
                event="anomaly", component="discovery", action="parse_repository_field",
                target="repository.url", outcome="missing_url", package_manager="npm"
            ))
            if is_debug_enabled(logger):
                logger.debug("Finished parsing repository field", extra=extra_context(
                    event="function_exit", component="discovery", action="parse_repository_field",
                    outcome="missing_url", package_manager="npm"
                ))
            return None, directory
        if is_debug_enabled(logger):
            logger.debug("Finished parsing repository field", extra=extra_context(
                event="function_exit", component="discovery", action="parse_repository_field",
                outcome="object", package_manager="npm"
            ))
        return url, directory

    if is_debug_enabled(logger):
        logger.warning("Repository field has unexpected type", extra=extra_context(
            event="anomaly", component="discovery", action="parse_repository_field",
            target="repository", outcome="unexpected_type", package_manager="npm"
        ))
        logger.debug("Finished parsing repository field", extra=extra_context(
            event="function_exit", component="discovery", action="parse_repository_field",
            outcome="unexpected_type", package_manager="npm"
        ))
    return None, None


def _extract_fallback_urls(version_info: Dict[str, Any]) -> List[str]:
    """Extract fallback repository URLs from homepage and bugs fields.

    Args:
        version_info: Version dictionary from packument

    Returns:
        List of candidate URLs from homepage and bugs.url
    """
    if is_debug_enabled(logger):
        logger.debug("Extracting fallback URLs", extra=extra_context(
            event="function_entry", component="discovery", action="extract_fallback_urls",
            package_manager="npm"
        ))
    candidates: List[str] = []

    # Homepage fallback
    homepage = version_info.get("homepage")
    if homepage:
        candidates.append(homepage)
        if is_debug_enabled(logger):
            logger.debug("Using homepage as fallback candidate", extra=extra_context(
                event="decision", component="discovery", action="extract_fallback_urls",
                target="homepage", outcome="added", package_manager="npm"
            ))

    # Bugs URL fallback - infer base repo from issues URLs
    bugs = version_info.get("bugs")
    if bugs:
        if isinstance(bugs, str):
            bugs_url = bugs
        elif isinstance(bugs, dict):
            bugs_url = bugs.get("url")
        else:
            bugs_url = None

        if bugs_url and "/issues" in bugs_url:
            # Infer base repository URL from issues URL
            base_repo_url = bugs_url.replace("/issues", "").replace("/issues/", "")
            candidates.append(base_repo_url)
            if is_debug_enabled(logger):
                logger.debug("Inferred repository URL from bugs/issues URL", extra=extra_context(
                    event="decision", component="discovery", action="extract_fallback_urls",
                    target="bugs", outcome="inferred_from_issues", package_manager="npm"
                ))
        elif bugs_url:
            if is_debug_enabled(logger):
                logger.debug("Bugs URL present but not issues URL", extra=extra_context(
                    event="decision", component="discovery", action="extract_fallback_urls",
                    target="bugs", outcome="not_issues_url", package_manager="npm"
                ))

    if is_debug_enabled(logger):
        logger.debug("Extracted fallback URLs", extra=extra_context(
            event="function_exit", component="discovery", action="extract_fallback_urls",
            count=len(candidates), package_manager="npm"
        ))

    return candidates
