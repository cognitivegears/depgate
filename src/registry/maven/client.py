"""Maven registry client and source scanner split from the former monolithic module."""
from __future__ import annotations

import json
import os
import sys
import time
import logging
import xml.etree.ElementTree as ET
from typing import List

from constants import ExitCodes, Constants
from common import http_client
from common.logging_utils import extra_context, is_debug_enabled, Timer, safe_url


logger = logging.getLogger(__name__)


def recv_pkg_info(pkgs, url: str = Constants.REGISTRY_URL_MAVEN) -> None:
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

        # Pre-call DEBUG log
        logger.debug(
            "HTTP request",
            extra=extra_context(
                event="http_request",
                component="client",
                action="GET",
                target=safe_url(url),
                package_manager="maven"
            )
        )

        with Timer() as timer:
            try:
                headers = {"Accept": "application/json", "Content-Type": "application/json"}
                # Sleep to avoid rate limiting
                time.sleep(0.1)
                res = http_client.safe_get(url, context="maven", params=payload, headers=headers)
            except SystemExit:
                # safe_get calls sys.exit on errors, so we need to catch and re-raise as exception
                logger.error(
                    "HTTP error",
                    exc_info=True,
                    extra=extra_context(
                        event="http_error",
                        outcome="exception",
                        target=safe_url(url),
                        package_manager="maven"
                    )
                )
                raise

        duration_ms = timer.duration_ms()

        if res.status_code == 200:
            if is_debug_enabled(logger):
                logger.debug(
                    "HTTP response ok",
                    extra=extra_context(
                        event="http_response",
                        outcome="success",
                        status_code=res.status_code,
                        duration_ms=duration_ms,
                        package_manager="maven"
                    )
                )
        else:
            logger.warning(
                "HTTP non-2xx handled",
                extra=extra_context(
                    event="http_response",
                    outcome="handled_non_2xx",
                    status_code=res.status_code,
                    duration_ms=duration_ms,
                    target=safe_url(url),
                    package_manager="maven"
                )
            )

        j = json.loads(res.text)
        number_found = j.get("response", {}).get("numFound", 0)
        if number_found == 1:  # safety, can't have multiples
            x.exists = True
            x.timestamp = j.get("response", {}).get("docs", [{}])[0].get("timestamp", 0)
            x.version_count = j.get("response", {}).get("docs", [{}])[0].get("versionCount", 0)
        elif number_found > 1:
            logging.warning("Multiple packages found, skipping")
            x.exists = False
        else:
            x.exists = False


def scan_source(dir_name: str, recursive: bool = False) -> List[str]:  # pylint: disable=too-many-locals
    """Scan the source directory for pom.xml files.

    Args:
        dir_name (str): Directory to scan.
        recursive (bool, optional): Whether to scan recursively. Defaults to False.

    Returns:
        List of discovered Maven coordinates in "group:artifact" form.
    """
    try:
        logging.info("Maven scanner engaged.")
        pom_files: List[str] = []
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

        lister: List[str] = []
        for pom_path in pom_files:
            tree = ET.parse(pom_path)
            pom = tree.getroot()
            ns = ".//{http://maven.apache.org/POM/4.0.0}"
            for dependencies in pom.findall(f"{ns}dependencies"):
                for dependency in dependencies.findall(f"{ns}dependency"):
                    # The original code tolerated missing nodes; preserve behavior
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
        # Preserve original behavior (no explicit exit here)
        return []
