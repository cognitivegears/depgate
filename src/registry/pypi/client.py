"""PyPI registry client: fetch package info and enrich with repository data."""
from __future__ import annotations

import json
import sys
import time
import logging
from datetime import datetime as dt
from packaging.requirements import Requirement
from constants import ExitCodes, Constants
from common.logging_utils import extra_context, is_debug_enabled, Timer, safe_url

import registry.pypi as pypi_pkg
from .enrich import _enrich_with_repo, _enrich_with_license

logger = logging.getLogger(__name__)

def _sanitize_identifier(identifier: str) -> str:
    """Return package name sans any version specifiers/extras/markers."""
    try:
        return Requirement(identifier).name
    except Exception:
        # Manual fallback for common separators and extras/markers
        for sep in ["===", ">=", "<=", "==", "~=", "!=", ">", "<"]:
            if sep in identifier:
                return identifier.split(sep)[0]
        if "[" in identifier:
            return identifier.split("[", 1)[0]
        if ";" in identifier:
            return identifier.split(";", 1)[0]
        return identifier

# Shared HTTP JSON headers and timestamp format for this module
HEADERS_JSON = {"Accept": "application/json", "Content-Type": "application/json"}
TIME_FORMAT_ISO = "%Y-%m-%dT%H:%M:%S.%fZ"

def _log_http_pre(url: str) -> None:
    """Debug-log outbound HTTP request for PyPI client."""
    logger.debug(
        "HTTP request",
        extra=extra_context(
            event="http_request",
            component="client",
            action="GET",
            target=safe_url(url),
            package_manager="pypi",
        ),
    )


def recv_pkg_info(pkgs, url: str = Constants.REGISTRY_URL_PYPI) -> None:
    """Check the existence of the packages in the PyPI registry.

    Args:
        pkgs (list): List of packages to check.
        url (str, optional): Url for PyPI. Defaults to Constants.REGISTRY_URL_PYPI.
    """
    logging.info("PyPI registry engaged.")
    for x in pkgs:
        # Sleep to avoid rate limiting
        time.sleep(0.1)
        name = getattr(x, "pkg_name", "")
        sanitized = _sanitize_identifier(str(name)).strip()
        fullurl = url + sanitized + "/json"

        # Pre-call DEBUG log via helper
        _log_http_pre(fullurl)

        with Timer() as timer:
            try:
                res = pypi_pkg.safe_get(fullurl, context="pypi", params=None, headers=HEADERS_JSON)
            except SystemExit:
                # safe_get calls sys.exit on errors, so we need to catch and re-raise as exception
                logger.error(
                    "HTTP error",
                    exc_info=True,
                    extra=extra_context(
                        event="http_error",
                        outcome="exception",
                        target=safe_url(fullurl),
                        package_manager="pypi",
                    ),
                )
                raise

        if res.status_code == 404:
            logger.warning(
                "HTTP 404 received; applying fallback",
                extra=extra_context(
                    event="http_response",
                    outcome="not_found_fallback",
                    status_code=404,
                    target=safe_url(fullurl),
                    package_manager="pypi",
                ),
            )
            # Package not found
            x.exists = False
            continue
        if res.status_code == 200:
            if is_debug_enabled(logger):
                logger.debug(
                    "HTTP response ok",
                    extra=extra_context(
                        event="http_response",
                        outcome="success",
                        status_code=res.status_code,
                        duration_ms=timer.duration_ms(),
                        package_manager="pypi",
                    ),
                )
        else:
            logger.warning(
                "HTTP non-2xx handled",
                extra=extra_context(
                    event="http_response",
                    outcome="handled_non_2xx",
                    status_code=res.status_code,
                    duration_ms=timer.duration_ms(),
                    target=safe_url(fullurl),
                    package_manager="pypi",
                ),
            )
            logging.error("Connection error, status code: %s", res.status_code)
            sys.exit(ExitCodes.CONNECTION_ERROR.value)

        try:
            j = json.loads(res.text)
        except json.JSONDecodeError:
            logging.warning("Couldn't decode JSON, assuming package missing.")
            x.exists = False
            continue

        if j.get("info"):
            x.exists = True
            latest = j["info"]["version"]
            # Extract timestamp for latest release if available
            try:
                timex = j["releases"][latest][0]["upload_time_iso_8601"]
                x.timestamp = int(dt.timestamp(dt.strptime(timex, TIME_FORMAT_ISO)) * 1000)
            except (ValueError, KeyError, IndexError):
                logging.warning("Couldn't parse timestamp, setting to 0.")
                x.timestamp = 0

            x.version_count = len(j.get("releases", {}))

            # Enrich with license metadata from PyPI info
            _enrich_with_license(x, j["info"])

            # Enrich with repository discovery and validation
            _enrich_with_repo(x, x.pkg_name, j["info"], latest)
        else:
            x.exists = False
