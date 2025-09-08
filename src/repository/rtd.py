"""Read the Docs repository resolution utilities.

Provides utilities to resolve repository URLs from Read the Docs
documentation URLs using the RTD v3 API.
"""
from __future__ import annotations

import re
from typing import Optional

from constants import Constants
from common.http_client import get_json


def infer_rtd_slug(url: Optional[str]) -> Optional[str]:
    """Parse Read the Docs slug from documentation URLs.

    Handles various RTD URL formats:
    - https://project.readthedocs.io/
    - https://readthedocs.org/projects/project/
    - https://project.readthedocs.io/en/latest/

    Args:
        url: The RTD documentation URL

    Returns:
        The project slug if found, None otherwise
    """
    if not url:
        return None

    url = url.strip()

    # Handle readthedocs.org/projects/slug format
    rtd_org_pattern = r'^https?://readthedocs\.org/projects/([^/]+)/?'
    match = re.match(rtd_org_pattern, url)
    if match:
        return match.group(1)

    # Handle *.readthedocs.io format
    rtd_io_pattern = r'^https?://([^.]+)\.readthedocs\.io/?'
    match = re.match(rtd_io_pattern, url)
    if match:
        return match.group(1)

    return None


def resolve_repo_from_rtd(rtd_url: str) -> Optional[str]:
    """Resolve repository URL from Read the Docs URL.

    Uses RTD v3 API to fetch project details and extract repository URL.
    Falls back through multiple strategies if initial lookup fails.

    Args:
        rtd_url: The RTD documentation URL

    Returns:
        Repository URL if found, None otherwise
    """
    slug = infer_rtd_slug(rtd_url)
    if not slug:
        return None

    # Try direct project detail endpoint
    detail_url = f"{Constants.READTHEDOCS_API_BASE}/projects/{slug}/"
    status, _, data = get_json(detail_url)

    if status == 200 and data and 'repository' in data:
        repo_url = data['repository'].get('url')
        if repo_url:
            return repo_url

    # Fallback: search by slug
    search_url = f"{Constants.READTHEDOCS_API_BASE}/projects/?slug={slug}"
    status, _, data = get_json(search_url)

    if status == 200 and data and 'results' in data and data['results']:
        repo_url = data['results'][0].get('repository', {}).get('url')
        if repo_url:
            return repo_url

    # Fallback: search by name
    name_search_url = f"{Constants.READTHEDOCS_API_BASE}/projects/?name={slug}"
    status, _, data = get_json(name_search_url)

    if status == 200 and data and 'results' in data and data['results']:
        repo_url = data['results'][0].get('repository', {}).get('url')
        if repo_url:
            return repo_url

    return None
