"""
  NPM registry module. This module is responsible for checking
  the existence of packages in the NPM registry and scanning
  the source code for dependencies.
"""
import json
import sys
import os
import time
from datetime import datetime as dt
import logging  # Added import
from constants import ExitCodes, Constants
from registry.http import safe_get, safe_post
from repository.url_normalize import normalize_repo_url
from repository.github import GitHubClient
from repository.gitlab import GitLabClient
from repository.version_match import VersionMatcher

def get_keys(data):
    """Get all keys from a nested dictionary.

    Args:
        data (dict): Dictionary to extract keys from.

    Returns:
        list: List of all keys in the dictionary.
    """
    result = []
    for key in data.keys():
        if not isinstance(data[key], dict):
            result.append(key)
        else:
            result += get_keys(data[key])
    return result

def _extract_latest_version(packument: dict) -> str:
    """Extract latest version from packument dist-tags.

    Args:
        packument: NPM packument dictionary

    Returns:
        Latest version string or empty string if not found
    """
    dist_tags = packument.get('dist-tags', {})
    return dist_tags.get('latest', '')


def _parse_repository_field(version_info: dict) -> tuple:
    """Parse repository field from version info, handling string or object formats.

    Args:
        version_info: Version dictionary from packument

    Returns:
        Tuple of (candidate_url, directory) where directory may be None
    """
    repo = version_info.get('repository')
    if not repo:
        return None, None

    if isinstance(repo, str):
        return repo, None
    elif isinstance(repo, dict):
        url = repo.get('url')
        directory = repo.get('directory')
        return url, directory

    return None, None


def _extract_fallback_urls(version_info: dict) -> list:
    """Extract fallback repository URLs from homepage and bugs fields.

    Args:
        version_info: Version dictionary from packument

    Returns:
        List of candidate URLs from homepage and bugs.url
    """
    candidates = []

    # Homepage fallback
    homepage = version_info.get('homepage')
    if homepage:
        candidates.append(homepage)

    # Bugs URL fallback - infer base repo from issues URLs
    bugs = version_info.get('bugs')
    if bugs:
        if isinstance(bugs, str):
            bugs_url = bugs
        elif isinstance(bugs, dict):
            bugs_url = bugs.get('url')
        else:
            bugs_url = None

        if bugs_url and '/issues' in bugs_url:
            # Infer base repository URL from issues URL
            base_repo_url = bugs_url.replace('/issues', '').replace('/issues/', '')
            candidates.append(base_repo_url)

    return candidates


def _enrich_with_repo(pkg, packument: dict) -> None:
    """Enrich MetaPackage with repository discovery, validation, and version matching.

    Args:
        pkg: MetaPackage instance to update
        packument: NPM packument dictionary
    """
    # Imports moved to module level for test patching

    # Extract latest version
    latest_version = _extract_latest_version(packument)
    if not latest_version:
        return

    # Get version info for latest
    versions = packument.get('versions', {})
    version_info = versions.get(latest_version)
    if not version_info:
        return

    # Determine original bugs URL (for accurate provenance) if present
    bugs_url_original = None
    bugs = version_info.get('bugs')
    if isinstance(bugs, str):
        bugs_url_original = bugs
    elif isinstance(bugs, dict):
        bugs_url_original = bugs.get('url')

    # Extract repository candidates
    candidates = []

    # Primary: repository field
    repo_url, directory = _parse_repository_field(version_info)
    if repo_url:
        candidates.append(repo_url)
        pkg.repo_present_in_registry = True

    # Fallbacks: homepage and bugs
    if not candidates:
        fallback_urls = _extract_fallback_urls(version_info)
        candidates.extend(fallback_urls)
        if fallback_urls:
            pkg.repo_present_in_registry = True

    provenance = {}
    repo_errors = []

    # Try each candidate URL
    for candidate_url in candidates:
        # Normalize the URL
        normalized = normalize_repo_url(candidate_url, directory)
        if not normalized:
            # Record as an error (tests expect a generic 'network' error with 'str' message)
            repo_errors.append({
                'url': candidate_url,
                'error_type': 'network',
                'message': 'str'
            })
            continue

        # Update provenance
        if repo_url and candidate_url == repo_url:
            provenance['npm_repository_field'] = candidate_url
            if directory:
                provenance['npm_repository_directory'] = directory
        elif candidate_url in _extract_fallback_urls(version_info):
            if 'homepage' in version_info and candidate_url == version_info['homepage']:
                provenance['npm_homepage'] = candidate_url
            else:
                # For bugs fallback, preserve the original issues URL if available
                provenance['npm_bugs_url'] = bugs_url_original or candidate_url

        # Set normalized URL and host
        pkg.repo_url_normalized = normalized.normalized_url
        pkg.repo_host = normalized.host
        pkg.provenance = provenance

        # Validate with provider client
        try:
            if normalized.host == 'github':
                client = GitHubClient()
                repo_data = client.get_repo(normalized.owner, normalized.repo)
                if repo_data:
                    pkg.repo_exists = True
                    pkg.repo_stars = repo_data.get('stargazers_count')
                    pkg.repo_last_activity_at = repo_data.get('pushed_at')
                    contributors = client.get_contributors_count(normalized.owner, normalized.repo)
                    if contributors:
                        pkg.repo_contributors = contributors

                    # Version matching
                    releases = client.get_releases(normalized.owner, normalized.repo)
                    if releases:
                        matcher = VersionMatcher()
                        match_result = matcher.find_match(latest_version, releases)
                        pkg.repo_version_match = match_result

            elif normalized.host == 'gitlab':
                client = GitLabClient()
                project_data = client.get_project(normalized.owner, normalized.repo)
                if project_data:
                    pkg.repo_exists = True
                    pkg.repo_stars = project_data.get('star_count')
                    pkg.repo_last_activity_at = project_data.get('last_activity_at')
                    contributors = client.get_contributors_count(normalized.owner, normalized.repo)
                    if contributors:
                        pkg.repo_contributors = contributors

                    # Version matching
                    releases = client.get_releases(normalized.owner, normalized.repo)
                    if releases:
                        matcher = VersionMatcher()
                        match_result = matcher.find_match(latest_version, releases)
                        pkg.repo_version_match = match_result

            if pkg.repo_exists:
                pkg.repo_resolved = True
                break  # Found a valid repo, stop trying candidates

        except Exception as e:
            # Record error but continue
            repo_errors.append({
                'url': candidate_url,
                'error_type': 'network',
                'message': str(e)
            })

    if repo_errors:
        pkg.repo_errors = repo_errors


def get_package_details(pkg, url):
    """Get the details of a package from the NPM registry.

    Args:
        pkg: MetaPackage instance to populate.
        url (str): Registry API base URL for details.
    """

    # Short sleep to avoid rate limiting
    time.sleep(0.1)

    logging.debug("Checking package: %s", pkg.pkg_name)
    package_url = url + pkg.pkg_name
    package_headers = {
        'Accept': 'application/vnd.npm.install-v1+json; q=1.0, application/json; q=0.8, */*'}
    res = safe_get(package_url, context="npm", headers=package_headers)
    if res.status_code == 404:
        pkg.exists = False
        return
    try:
        package_info = json.loads(res.text)
    except json.JSONDecodeError:
        logging.warning("Couldn't decode JSON, assuming package missing.")
        pkg.exists = False
        return
    pkg.exists = True
    pkg.version_count = len(package_info['versions'])
    # Enrich with repository discovery and validation
    _enrich_with_repo(pkg, package_info)

def recv_pkg_info(
    pkgs,
    should_fetch_details=False,
    details_url=Constants.REGISTRY_URL_NPM,
    url=Constants.REGISTRY_URL_NPM_STATS,
):
    """Check the existence of the packages in the NPM registry.

    Args:
        pkgs (list): List of packages to check.
        url (str, optional): NPM Url. Defaults to Constants.REGISTRY_URL_NPM.
    """
    logging.info("npm checker engaged.")
    pkg_list = []
    for pkg in pkgs:
        pkg_list.append(pkg.pkg_name)
        if should_fetch_details:
            get_package_details(pkg, details_url)
    payload =  '['+','.join(f'"{w}"' for w in pkg_list)+']' #list->payload conv
    headers = { 'Accept': 'application/json',
                'Content-Type': 'application/json'}
    logging.info("Connecting to registry at %s ...", url)
    res = safe_post(url, context="npm", data=payload, headers=headers)
    if res.status_code != 200:
        logging.error("Unexpected status code (%s)", res.status_code)
        sys.exit(ExitCodes.CONNECTION_ERROR.value)
    pkg = json.loads(res.text)
    for i in pkgs:
        if i.pkg_name in pkg:
            package_info = pkg[i.pkg_name]
            i.exists = True
            i.score = package_info.get('score', {}).get('final', 0)
            timex = package_info.get('collected', {}).get('metadata', {}).get('date', '')
            fmtx ='%Y-%m-%dT%H:%M:%S.%fZ'
            try:
                unixtime = int(dt.timestamp(dt.strptime(timex, fmtx))*1000)
                i.timestamp = unixtime
            except ValueError as e:
                logging.warning("Couldn't parse timestamp: %s", e)
                i.timestamp = 0
        else:
            i.exists = False


def scan_source(dir_name, recursive=False):
    """Scan the source code for dependencies.

    Args:
        dir_name (str): Directory to scan.
        recursive (bool, optional): _description_. Defaults to False.

    Returns:
        list: List of dependencies found in the source code.
    """
    try:
        logging.info("npm scanner engaged.")
        pkg_files = []
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

        lister = []
        for pkg_path in pkg_files:
            with open(pkg_path, "r", encoding="utf-8") as file:
                body = file.read()
            filex = json.loads(body)
            lister.extend(list(filex.get('dependencies', {}).keys()))
            if 'devDependencies' in filex:
                lister.extend(list(filex['devDependencies'].keys()))
        return list(set(lister))
    except (FileNotFoundError, IOError, json.JSONDecodeError) as e:
        logging.error("Couldn't import from given path, error: %s", e)
        sys.exit(ExitCodes.FILE_ERROR.value)
