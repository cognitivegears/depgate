"""NPM registry client: package details and bulk stats."""

from __future__ import annotations

import json
import sys
import time
import logging
from datetime import datetime as dt

from constants import ExitCodes, Constants
from common.http_client import safe_get, safe_post
from common.logging_utils import extra_context, is_debug_enabled, Timer, safe_url, redact

from .enrich import _enrich_with_repo
import registry.npm as npm_pkg

logger = logging.getLogger(__name__)


def get_package_details(pkg, url: str) -> None:
    """Get the details of a package from the NPM registry.

    Args:
        pkg: MetaPackage instance to populate.
        url: Registry API base URL for details.
    """
    # Short sleep to avoid rate limiting
    time.sleep(0.1)

    logging.debug("Checking package: %s", pkg.pkg_name)
    package_url = url + pkg.pkg_name
    package_headers = {
        "Accept": "application/vnd.npm.install-v1+json; q=1.0, application/json; q=0.8, */*"
    }

    # Pre-call DEBUG log
    # Encode brackets in '[REDACTED]' for URL consistency in logs
    safe_target = safe_url(package_url).replace("[REDACTED]", "%5BREDACTED%5D")
    logger.debug(
        "HTTP request",
        extra=extra_context(
            event="http_request",
            component="client",
            action="GET",
            target=safe_target,
            package_manager="npm"
        )
    )

    with Timer() as timer:
        try:
            res = npm_pkg.safe_get(package_url, context="npm", headers=package_headers)
        except SystemExit:
            # safe_get calls sys.exit on errors, so we need to catch and re-raise as exception
            logger.error(
                "HTTP error",
                exc_info=True,
                extra=extra_context(
                    event="http_error",
                    outcome="exception",
                    target=safe_url(package_url),
                    package_manager="npm"
                )
            )
            raise

    duration_ms = timer.duration_ms()

    if res.status_code == 404:
        logger.warning(
            "HTTP 404 received; applying fallback",
            extra=extra_context(
                event="http_response",
                outcome="not_found_fallback",
                status_code=404,
                target=safe_url(package_url),
                package_manager="npm"
            )
        )
        pkg.exists = False
        return
    elif res.status_code >= 200 and res.status_code < 300:
        if is_debug_enabled(logger):
            logger.debug(
                "HTTP response ok",
                extra=extra_context(
                    event="http_response",
                    outcome="success",
                    status_code=res.status_code,
                    duration_ms=duration_ms,
                    package_manager="npm"
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
                target=safe_url(package_url),
                package_manager="npm"
            )
        )
        # For non-2xx non-404, we continue processing but log the issue

    try:
        package_info = json.loads(res.text)
    except json.JSONDecodeError:
        logging.warning("Couldn't decode JSON, assuming package missing.")
        pkg.exists = False
        return
    pkg.exists = True
    pkg.version_count = len(package_info["versions"])
    # Enrich with repository discovery and validation
    _enrich_with_repo(pkg, package_info)


def recv_pkg_info(
    pkgs,
    should_fetch_details: bool = False,
    details_url: str = Constants.REGISTRY_URL_NPM,
    url: str = Constants.REGISTRY_URL_NPM_STATS,
) -> None:
    """Check the existence of the packages in the NPM registry.

    Args:
        pkgs (list): List of packages to check.
        url (str, optional): NPM Url. Defaults to Constants.REGISTRY_URL_NPM_STATS.
    """
    logging.info("npm checker engaged.")
    pkg_list = []
    for pkg in pkgs:
        pkg_list.append(pkg.pkg_name)
        if should_fetch_details:
            get_package_details(pkg, details_url)
    payload = "[" + ",".join(f'"{w}"' for w in pkg_list) + "]"  # list->payload conv
    headers = {"Accept": "application/json", "Content-Type": "application/json"}

    # Pre-call DEBUG log
    safe_target_stats = safe_url(url).replace("[REDACTED]", "%5BREDACTED%5D")
    logger.debug(
        "HTTP request",
        extra=extra_context(
            event="http_request",
            component="client",
            action="POST",
            target=safe_target_stats,
            package_manager="npm"
        )
    )

    with Timer() as timer:
        try:
            res = npm_pkg.safe_post(url, context="npm", data=payload, headers=headers)
        except SystemExit:
            # safe_post calls sys.exit on errors, so we need to catch and re-raise as exception
            logger.error(
                "HTTP error",
                exc_info=True,
                extra=extra_context(
                    event="http_error",
                    outcome="exception",
                    target=safe_url(url),
                    package_manager="npm"
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
                    package_manager="npm"
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
                package_manager="npm"
            )
        )
        logging.error("Unexpected status code (%s)", res.status_code)
        sys.exit(ExitCodes.CONNECTION_ERROR.value)

    pkg_map = json.loads(res.text)
    for i in pkgs:
        if i.pkg_name in pkg_map:
            package_info = pkg_map[i.pkg_name]
            i.exists = True
            i.score = package_info.get("score", {}).get("final", 0)
            timex = package_info.get("collected", {}).get("metadata", {}).get("date", "")
            fmtx = "%Y-%m-%dT%H:%M:%S.%fZ"
            try:
                unixtime = int(dt.timestamp(dt.strptime(timex, fmtx)) * 1000)
                i.timestamp = unixtime
            except ValueError as e:
                logging.warning("Couldn't parse timestamp: %s", e)
                i.timestamp = 0
        else:
            i.exists = False
