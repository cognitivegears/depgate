"""Maven registry interaction module."""
import json
import os
import sys
import time
import logging
import xml.etree.ElementTree as ET
from constants import ExitCodes, Constants
from registry.http import safe_get
from typing import Optional, Dict, Any
from repository.url_normalize import normalize_repo_url
from repository.github import GitHubClient
from repository.gitlab import GitLabClient
from repository.version_match import VersionMatcher
from repository.providers import ProviderType, map_host_to_type
from repository.provider_registry import ProviderRegistry
from repository.provider_validation import ProviderValidationService

def recv_pkg_info(pkgs, url=Constants.REGISTRY_URL_MAVEN):
    """Check the existence of the packages in the Maven registry.

    Args:
        pkgs (list): List of packages to check.
        url (str, optional): Maven Url. Defaults to Constants.REGISTRY_URL_MAVEN.
    """
    logging.info("Maven checker engaged.")
    payload = {"wt": "json", "rows": 20}
    # NOTE: move everything off names and modify instances instead
    for x in pkgs:
        tempstring = "g:" + x.org_id + " a:" + x.pkg_name
        payload.update({"q": tempstring})
        headers = { 'Accept': 'application/json',
                'Content-Type': 'application/json'}
        # Sleep to avoid rate limiting
        time.sleep(0.1)
        res = safe_get(url, context="maven", params=payload, headers=headers)

        j = json.loads(res.text)
        number_found = j.get('response', {}).get('numFound', 0)
        if number_found == 1: #safety, can't have multiples
            x.exists = True
            x.timestamp = j.get('response', {}).get('docs', [{}])[0].get('timestamp', 0)
            x.version_count = j.get('response', {}).get('docs', [{}])[0].get('versionCount', 0)
        elif number_found > 1:
            logging.warning("Multiple packages found, skipping")
            x.exists = False
        else:
            x.exists = False

def scan_source(dir_name, recursive=False):  # pylint: disable=too-many-locals
    """Scan the source directory for pom.xml files.

    Args:
        dir_name (str): Directory to scan.
        recursive (bool, optional): Whether to scan recursively. Defaults to False.

    Returns:
        _type_: _description_
    """
    try:
        logging.info("Maven scanner engaged.")
        pom_files = []
        if recursive:
            for root, _, files in os.walk(dir_name):
                if Constants.POM_XML_FILE in files:
                    pom_files.append(os.path.join(root, Constants.POM_XML_FILE))
        else:
            path = os.path.join(dir_name, Constants.POM_XML_FILE)
            if os.path.isfile(path):
                pom_files.append(path)
            else:
                logging.error("pom.xml not found. Unable to scan.")
                sys.exit(ExitCodes.FILE_ERROR.value)

        lister = []
        for pom_path in pom_files:
            tree = ET.parse(pom_path)
            pom = tree.getroot()
            ns = ".//{http://maven.apache.org/POM/4.0.0}"
            for dependencies in pom.findall(f"{ns}dependencies"):
                for dependency in dependencies.findall(f"{ns}dependency"):
                    group_node = dependency.find(f"{ns}groupId")
                    if group_node is None or group_node.text is None:
                        continue
                    group = group_node.text
                    artifact_node = dependency.find(f"{ns}artifactId")
                    if artifact_node is None or artifact_node.text is None:
                        continue
                    artifact = artifact_node.text
                    lister.append(f"{group}:{artifact}")
        return list(set(lister))
    except (FileNotFoundError, ET.ParseError) as e:
        logging.error("Couldn't import from given path, error: %s", e)
def _resolve_latest_version(group: str, artifact: str) -> Optional[str]:
    """Resolve latest release version from Maven metadata.

    Args:
        group: Maven group ID
        artifact: Maven artifact ID

    Returns:
        Latest release version string or None if not found
    """
    # Convert group to path format
    group_path = group.replace('.', '/')
    metadata_url = f"https://repo1.maven.org/maven2/{group_path}/{artifact}/maven-metadata.xml"

    try:
        response = safe_get(metadata_url, context="maven")
        if response.status_code != 200:
            return None

        # Parse XML to find release version
        root = ET.fromstring(response.text)
        versioning = root.find('versioning')
        if versioning is not None:
            # Try release first, then latest
            release_elem = versioning.find('release')
            if release_elem is not None and release_elem.text:
                return release_elem.text

            latest_elem = versioning.find('latest')
            if latest_elem is not None and latest_elem.text:
                return latest_elem.text

    except (ET.ParseError, AttributeError):
        logging.debug(f"Failed to parse Maven metadata for {group}:{artifact}")

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
    group_path = group.replace('.', '/')
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
    try:
        response = safe_get(pom_url, context="maven")
        if response.status_code == 200:
            return response.text
    except Exception as e:
        logging.debug(f"Failed to fetch POM for {group}:{artifact}:{version}: {e}")

    return None

def _parse_scm_from_pom(pom_xml: str) -> Dict[str, Any]:
    """Parse SCM information from POM XML.

    Args:
        pom_xml: POM XML content as string

    Returns:
        Dict containing SCM info and parent info
    """
    result: Dict[str, Any] = {
        'url': None,
        'connection': None,
        'developerConnection': None,
        'parent': None
    }

    try:
        root = ET.fromstring(pom_xml)
        ns = ".//{http://maven.apache.org/POM/4.0.0}"

        # Parse SCM block
        scm_elem = root.find(f"{ns}scm")
        if scm_elem is not None:
            url_elem = scm_elem.find(f"{ns}url")
            if url_elem is not None:
                result['url'] = url_elem.text

            conn_elem = scm_elem.find(f"{ns}connection")
            if conn_elem is not None:
                result['connection'] = conn_elem.text

            dev_conn_elem = scm_elem.find(f"{ns}developerConnection")
            if dev_conn_elem is not None:
                result['developerConnection'] = dev_conn_elem.text

        # Parse parent block
        parent_elem = root.find(f"{ns}parent")
        if parent_elem is not None:
            parent_info = {}
            for field in ['groupId', 'artifactId', 'version']:
                field_elem = parent_elem.find(f"{ns}{field}")
                if field_elem is not None:
                    parent_info[field] = field_elem.text
            if parent_info:
                result['parent'] = parent_info

    except (ET.ParseError, AttributeError) as e:
        logging.debug(f"Failed to parse POM XML: {e}")

    return result

def _normalize_scm_to_repo_url(scm: Dict[str, Any]) -> Optional[str]:
    """Normalize SCM connection strings to repository URL.

    Args:
        scm: SCM dictionary from _parse_scm_from_pom

    Returns:
        Normalized repository URL or None
    """
    from repository.url_normalize import normalize_repo_url

    # Try different SCM fields in priority order
    candidates = []
    if scm.get('url'):
        candidates.append(scm['url'])
    if scm.get('connection'):
        candidates.append(scm['connection'])
    if scm.get('developerConnection'):
        candidates.append(scm['developerConnection'])

    for candidate in candidates:
        normalized = normalize_repo_url(candidate)
        if normalized:
            return normalized.normalized_url

    return None

def _traverse_for_scm(group: str, artifact: str, version: str, provenance: Dict[str, Any], depth: int = 0, max_depth: int = 8) -> Dict[str, Any]:
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
    if scm_info.get('url') or scm_info.get('connection') or scm_info.get('developerConnection'):
        if depth > 0:
            provenance[f"maven_parent_pom.depth{depth}.scm.url"] = scm_info.get('url')
            provenance[f"maven_parent_pom.depth{depth}.scm.connection"] = scm_info.get('connection')
            provenance[f"maven_parent_pom.depth{depth}.scm.developerConnection"] = scm_info.get('developerConnection')
        else:
            provenance["maven_pom.scm.url"] = scm_info.get('url')
            provenance["maven_pom.scm.connection"] = scm_info.get('connection')
            provenance["maven_pom.scm.developerConnection"] = scm_info.get('developerConnection')
        return scm_info

    # If no SCM but has parent, traverse up
    if scm_info.get('parent'):
        parent = scm_info['parent']
        parent_group = parent.get('groupId')
        parent_artifact = parent.get('artifactId')
        parent_version = parent.get('version')

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
            if 'github.com' in url or 'gitlab.com' in url:
                return url
    except (ET.ParseError, AttributeError):
        pass

    return None

def _enrich_with_repo(mp, group: str, artifact: str, version: Optional[str]) -> None:
    """Enrich MetaPackage with repository discovery, validation, and version matching.

    Args:
        mp: MetaPackage instance to update
        group: Maven group ID
        artifact: Maven artifact ID
        version: Version string (may be None)
    """
    # imports are at module scope for easier test patching

    # Resolve version if not provided
    if not version:
        version = _resolve_latest_version(group, artifact)
        if version:
            provenance = mp.provenance or {}
            provenance['maven_metadata.release'] = version
            mp.provenance = provenance

    if not version:
        return

    provenance = mp.provenance or {}
    repo_errors = []

    # Try to get SCM from POM traversal
    scm_info = _traverse_for_scm(group, artifact, version, provenance)
    # Allow _traverse_for_scm to return either a plain SCM dict or a wrapper with keys
    # 'scm' (dict) and optional 'provenance' (dict) for additional context.
    if isinstance(scm_info, dict) and 'provenance' in scm_info and isinstance(scm_info['provenance'], dict):
        # Merge any provenance supplied by traversal
        provenance.update(scm_info['provenance'])
        mp.provenance = provenance
    if isinstance(scm_info, dict) and 'scm' in scm_info and isinstance(scm_info['scm'], dict):
        scm_info = scm_info['scm']

    candidates = []

    # Primary: SCM from POM
    if scm_info:
        repo_url = _normalize_scm_to_repo_url(scm_info)
        if repo_url:
            candidates.append(repo_url)
            mp.repo_present_in_registry = True

    # Fallback: <url> field from POM
    if not candidates:
        pom_xml = _fetch_pom(group, artifact, version)
        if pom_xml:
            fallback_url = _url_fallback_from_pom(pom_xml)
            if fallback_url:
                candidates.append(fallback_url)
                mp.repo_present_in_registry = True
                provenance['maven_pom.url_fallback'] = fallback_url

    # Try each candidate URL
    for candidate_url in candidates:
        # Normalize the URL
        normalized = normalize_repo_url(candidate_url)
        if not normalized:
            continue

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
                'url': candidate_url,
                'error_type': 'network',
                'message': str(e)
            })

    if repo_errors:
        mp.repo_errors = repo_errors
