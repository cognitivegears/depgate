"""Maven registry interaction module."""
import json
import os
import sys
import time
import logging
import xml.etree.ElementTree as ET
from constants import ExitCodes, Constants
from registry.http import safe_get

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
        sys.exit(ExitCodes.FILE_ERROR.value)
