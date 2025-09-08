"""PyPI registry module."""
import json
import sys
import os
import time
from datetime import datetime as dt
import logging  # Added import
import requirements
from constants import ExitCodes, Constants
from common.http_client import safe_get
from typing import Optional, List
from repository.url_normalize import normalize_repo_url
from repository.github import GitHubClient
from repository.gitlab import GitLabClient
from repository.version_match import VersionMatcher
from repository.rtd import infer_rtd_slug, resolve_repo_from_rtd
from repository.providers import ProviderType, map_host_to_type
from repository.provider_registry import ProviderRegistry
from repository.provider_validation import ProviderValidationService

# Compatibility alias for tests that patch using 'src.registry.pypi'
# Ensures patch('src.registry.pypi.*') targets the same module object as 'registry.pypi'
import sys as _sys  # noqa: E402
if 'src.registry.pypi' not in _sys.modules:
    _sys.modules['src.registry.pypi'] = _sys.modules[__name__]
def recv_pkg_info(pkgs, url=Constants.REGISTRY_URL_PYPI):
    """Check the existence of the packages in the PyPI registry.

    Args:
        pkgs (list): List of packages to check.
        url (str, optional): Url for PyPi. Defaults to Constants.REGISTRY_URL_PYPI.
    """
    logging.info("PyPI registry engaged.")
    payload = {}
    for x in pkgs:
        # Sleep to avoid rate limiting
        time.sleep(0.1)
        fullurl = url + x.pkg_name + '/json'
        logging.debug(fullurl)
        headers = {'Accept': 'application/json',
                   'Content-Type': 'application/json'}
        res = safe_get(fullurl, context="pypi", params=payload, headers=headers)
        if res.status_code == 404:
            # Package not found
            x.exists = False
            continue
        if res.status_code != 200:
            logging.error("Connection error, status code: %s", res.status_code)
            sys.exit(ExitCodes.CONNECTION_ERROR.value)
        try:
            j = json.loads(res.text)
        except json.JSONDecodeError:
            logging.warning("Couldn't decode JSON, assuming package missing.")
            x.exists = False
            continue
        if j['info']:
            x.exists = True
            latest = j['info']['version']
            for version in j['releases']:
                if version == latest:
                    timex = j['releases'][version][0]['upload_time_iso_8601']
                    fmtx = '%Y-%m-%dT%H:%M:%S.%fZ'
                    try:
                        unixtime = int(dt.timestamp(dt.strptime(timex, fmtx)) * 1000)
                        x.timestamp = unixtime
                    except ValueError as e:
                        logging.warning("Couldn't parse timestamp %s, setting to 0.", e)
                        x.timestamp = 0
            x.version_count = len(j['releases'])

            # Enrich with repository discovery and validation
            _enrich_with_repo(x, x.pkg_name, j['info'], latest)
        else:
            x.exists = False
def _extract_repo_candidates(info: dict) -> List[str]:
    """Extract repository candidate URLs from PyPI package info.

    Returns ordered list of candidate URLs from project_urls and home_page.
    Prefers explicit repository/source keys first, then docs/homepage.

    Args:
        info: PyPI package info dict

    Returns:
        List of candidate URLs in priority order
    """
    candidates = []
    project_urls = info.get('project_urls', {}) or {}

    # Priority 1: Explicit repository/source keys in project_urls
    repo_keys = [
        'repository', 'source', 'source code', 'code',
        'project-urls.repository', 'project-urls.source'
    ]
    repo_candidates = [
        url for key, url in project_urls.items()
        if url and any(repo_key.lower() in key.lower() for repo_key in repo_keys)
    ]

    # If repo links exist, include them and any explicit documentation/docs links (but not homepage)
    if repo_candidates:
        doc_keys_strict = ['documentation', 'docs']
        doc_candidates = [
            url for key, url in project_urls.items()
            if url and any(doc_key.lower() in key.lower() for doc_key in doc_keys_strict)
        ]
        return repo_candidates + doc_candidates

    # Priority 2: Documentation/homepage keys that might point to repos (when no explicit repo present)
    doc_keys = ['documentation', 'docs', 'homepage', 'home page']
    for key, url in project_urls.items():
        if url and any(doc_key.lower() in key.lower() for doc_key in doc_keys):
            candidates.append(url)

    # Priority 3: info.home_page as weak fallback
    home_page = info.get('home_page')
    if home_page:
        candidates.append(home_page)

    return candidates


def _maybe_resolve_via_rtd(url: str) -> Optional[str]:
    """Resolve repository URL from Read the Docs URL if applicable.

    Args:
        url: Potential RTD URL

    Returns:
        Repository URL if RTD resolution succeeds, None otherwise
    """
    if not url:
        return None

    slug = infer_rtd_slug(url)
    if slug:
        return resolve_repo_from_rtd(url)

    return None


def _enrich_with_repo(mp, name: str, info: dict, version: str) -> None:
    """Enrich MetaPackage with repository discovery, validation, and version matching.

    Args:
        mp: MetaPackage instance to update
        name: Package name
        info: PyPI package info dict
        version: Package version string
    """
    # Imports moved to module level for test patching

    candidates = _extract_repo_candidates(info)
    mp.repo_present_in_registry = bool(candidates)

    provenance = {}
    repo_errors = []

    # Try each candidate URL
    for candidate_url in candidates:
        # Only try RTD resolution for RTD-hosted docs URLs
        if ('readthedocs.io' in candidate_url) or ('readthedocs.org' in candidate_url):
            rtd_repo_url = _maybe_resolve_via_rtd(candidate_url)
            if rtd_repo_url:
                final_url = rtd_repo_url
                provenance['rtd_slug'] = infer_rtd_slug(candidate_url)
                provenance['rtd_source'] = 'detail'  # Simplified
            else:
                final_url = candidate_url
        else:
            final_url = candidate_url

        # Normalize the URL
        normalized = normalize_repo_url(final_url)
        if not normalized:
            continue

        # Update provenance
        if 'rtd_slug' not in provenance:
            provenance['pypi_project_urls'] = final_url
        if final_url != normalized.normalized_url:
            provenance['normalization_changed'] = True

        # Set normalized URL and host
        mp.repo_url_normalized = normalized.normalized_url
        mp.repo_host = normalized.host
        mp.provenance = provenance

        # Validate with provider client
        try:
            ptype = map_host_to_type(normalized.host)
            if ptype != ProviderType.UNKNOWN:
                injected = (
                    {'github': GitHubClient()}
                    if ptype == ProviderType.GITHUB
                    else {'gitlab': GitLabClient()}
                )
                provider = ProviderRegistry.get(ptype, injected)  # type: ignore
                ProviderValidationService.validate_and_populate(
                    mp, normalized, version, provider, VersionMatcher()
                )
            if mp.repo_exists:
                mp.repo_resolved = True
                break  # Found a valid repo, stop trying candidates

        except Exception as e:
            # Record error but continue
            repo_errors.append({
                'url': final_url,
                'error_type': 'network',
                'message': str(e)
            })

    if repo_errors:
        mp.repo_errors = repo_errors

def scan_source(dir_name, recursive=False):
    """Scan the source directory for requirements.txt files.

    Args:
        dir_name (str): Directory to scan.
        recursive (bool, optional): Whether to recurse into subdirectories. Defaults to False.

    Raises:
        FileNotFoundError: _description_

    Returns:
        _type_: _description_
    """
    current_path = ""
    try:
        logging.info("PyPI scanner engaged.")
        req_files = []
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

        all_requirements = []
        for req_path in req_files:
            with open(req_path, "r", encoding="utf-8") as file:
                body = file.read()
            reqs = requirements.parse(body)
            all_requirements.extend([x.name for x in reqs])
        return list(set(all_requirements))
    except (FileNotFoundError, IOError) as e:
        logging.error("Couldn't import from given path '%s', error: %s", current_path, e)
        sys.exit(ExitCodes.FILE_ERROR.value)
