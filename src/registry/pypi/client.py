"""PyPI registry client: fetch package info and enrich with repository data."""
from __future__ import annotations

import json
import sys
import time
import logging
from datetime import datetime as dt
from typing import List

from constants import ExitCodes, Constants
from common.http_client import safe_get
from common.logging_utils import extra_context, is_debug_enabled, Timer, safe_url, redact

from .enrich import _enrich_with_repo
import registry.pypi as pypi_pkg

logger = logging.getLogger(__name__)


def recv_pkg_info(pkgs, url: str = Constants.REGISTRY_URL_PYPI) -> None:
    """Check the existence of the packages in the PyPI registry.

    Args:
        pkgs (list): List of packages to check.
        url (str, optional): Url for PyPI. Defaults to Constants.REGISTRY_URL_PYPI.
    """
    logging.info("PyPI registry engaged.")
    payload = {}
    for x in pkgs:
        # Sleep to avoid rate limiting
        time.sleep(0.1)
        fullurl = url + x.pkg_name + "/json"

        # Pre-call DEBUG log
        logger.debug(
            "HTTP request",
            extra=extra_context(
                event="http_request",
                component="client",
                action="GET",
                target=safe_url(fullurl),
                package_manager="pypi"
            )
        )

        with Timer() as timer:
            try:
                headers = {"Accept": "application/json", "Content-Type": "application/json"}
                res = pypi_pkg.safe_get(fullurl, context="pypi", params=payload, headers=headers)
            except SystemExit:
                # safe_get calls sys.exit on errors, so we need to catch and re-raise as exception
                logger.error(
                    "HTTP error",
                    exc_info=True,
                    extra=extra_context(
                        event="http_error",
                        outcome="exception",
                        target=safe_url(fullurl),
                        package_manager="pypi"
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
                    target=safe_url(fullurl),
                    package_manager="pypi"
                )
            )
            # Package not found
            x.exists = False
            continue
        elif res.status_code == 200:
            if is_debug_enabled(logger):
                logger.debug(
                    "HTTP response ok",
                    extra=extra_context(
                        event="http_response",
                        outcome="success",
                        status_code=res.status_code,
                        duration_ms=duration_ms,
                        package_manager="pypi"
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
                    target=safe_url(fullurl),
                    package_manager="pypi"
                )
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
            for version in j.get("releases", {}):
                if version == latest:
                    try:
                        timex = j["releases"][version][0]["upload_time_iso_8601"]
                        fmtx = "%Y-%m-%dT%H:%M:%S.%fZ"
                        unixtime = int(dt.timestamp(dt.strptime(timex, fmtx)) * 1000)
                        x.timestamp = unixtime
                    except (ValueError, KeyError, IndexError) as e:
                        logging.warning("Couldn't parse timestamp %s, setting to 0.", e)
                        x.timestamp = 0
            x.version_count = len(j.get("releases", {}))

            # Enrich with repository discovery and validation
            _enrich_with_repo(x, x.pkg_name, j["info"], latest)
        else:
            x.exists = False
