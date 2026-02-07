"""PyPI registry client: fetch package info and enrich with repository data."""
from __future__ import annotations

import json
import sys
import time
import logging
from datetime import datetime as dt
from typing import Optional, Dict, Any, List, Tuple
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from constants import ExitCodes, Constants
from common.logging_utils import extra_context, is_debug_enabled, Timer, safe_url
from common.trust_signals import score_from_boolean_signals, regressed, score_delta, epoch_ms_from_iso8601

import registry.pypi as pypi_pkg
from .enrich import _enrich_with_repo, _enrich_with_license

logger = logging.getLogger(__name__)

# pypistats.org API endpoint for recent download stats
PYPSTATS_RECENT_URL = "https://pypistats.org/api/packages/{package}/recent"

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
HEADERS_SIMPLE_JSON = {"Accept": "application/vnd.pypi.simple.v1+json"}

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


def _fetch_weekly_downloads(package_name: str) -> Optional[int]:
    """Fetch weekly downloads for a package from pypistats.org.

    Args:
        package_name: Sanitized package name.

    Returns:
        Weekly download count or None if unavailable.
    """
    stats_url = PYPSTATS_RECENT_URL.format(package=package_name)

    try:
        res = pypi_pkg.safe_get(stats_url, context="pypistats", params=None, headers=HEADERS_JSON)
    except SystemExit:
        logger.warning("pypistats fetch failed; skipping weekly downloads")
        return None

    if res.status_code != 200:
        return None

    try:
        stats = json.loads(res.text)
    except json.JSONDecodeError:
        return None

    return stats.get("data", {}).get("last_week")


def _release_timestamp_ms(release_files: List[Dict[str, Any]]) -> Optional[int]:
    """Extract latest upload timestamp for a release file list."""
    latest_ms = None
    for file_info in release_files:
        if not isinstance(file_info, dict):
            continue
        iso = file_info.get("upload_time_iso_8601") or file_info.get("upload_time")
        parsed = epoch_ms_from_iso8601(iso if isinstance(iso, str) else None)
        if parsed is not None and (latest_ms is None or parsed > latest_ms):
            latest_ms = parsed
    return latest_ms


def _ordered_release_versions(releases: Dict[str, Any]) -> List[str]:
    """Return releases ordered by upload timestamp (oldest->newest)."""
    pairs: List[Tuple[int, str]] = []
    for ver, files in releases.items():
        if not isinstance(files, list):
            continue
        ts = _release_timestamp_ms(files)
        if ts is not None:
            pairs.append((ts, ver))
    if not pairs:
        return list(releases.keys())
    pairs.sort(key=lambda p: p[0])
    return [ver for _, ver in pairs]


def _fetch_simple_index_json(normalized_name: str) -> Optional[Dict[str, Any]]:
    """Fetch PyPI Simple API JSON payload for a package."""
    url = f"https://pypi.org/simple/{normalized_name}/"
    try:
        res = pypi_pkg.safe_get(url, context="pypi", params=None, headers=HEADERS_SIMPLE_JSON)
    except (SystemExit, StopIteration):
        return None
    except Exception:
        return None
    if res.status_code != 200:
        return None
    try:
        payload = json.loads(res.text)
    except json.JSONDecodeError:
        return None
    if isinstance(payload, dict):
        return payload
    return None


def _extract_simple_trust(simple_json: Optional[Dict[str, Any]], version: str) -> tuple[Optional[bool], Optional[bool], Optional[str]]:
    """Return (registry_signature_present, provenance_present, provenance_url)."""
    if not isinstance(simple_json, dict):
        return None, None, None
    files = simple_json.get("files", [])
    if not isinstance(files, list):
        return None, None, None

    version_files = []
    for file_entry in files:
        if not isinstance(file_entry, dict):
            continue
        if str(file_entry.get("version", "")) == str(version):
            version_files.append(file_entry)
    if not version_files:
        return None, None, None

    has_signature = False
    has_provenance = False
    provenance_url = None
    for entry in version_files:
        if bool(entry.get("gpg-sig")):
            has_signature = True
        prov = entry.get("provenance")
        if prov:
            has_provenance = True
            if isinstance(prov, str) and prov.strip() and provenance_url is None:
                provenance_url = prov.strip()
            elif isinstance(prov, dict) and provenance_url is None:
                url = prov.get("url")
                if isinstance(url, str) and url.strip():
                    provenance_url = url.strip()
    return has_signature, has_provenance, provenance_url


def _extract_legacy_json_signature(releases: Dict[str, Any], version: str) -> Optional[bool]:
    """Fallback signature signal from Warehouse JSON `has_sig` field."""
    files = releases.get(version)
    if not isinstance(files, list) or not files:
        return None
    return any(bool((f or {}).get("has_sig")) for f in files if isinstance(f, dict))


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
        normalized = canonicalize_name(sanitized)
        fullurl = url + normalized + "/json"

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
            releases = j.get("releases", {}) or {}
            x.version_count = len(releases)

            selected_version = getattr(x, "resolved_version", None)
            if not isinstance(selected_version, str) or selected_version not in releases:
                selected_version = latest

            # Extract timestamp for selected release if available
            release_files = releases.get(selected_version, []) if isinstance(releases, dict) else []
            selected_ts = _release_timestamp_ms(release_files if isinstance(release_files, list) else [])
            if selected_ts is not None:
                x.timestamp = selected_ts
            else:
                # Keep legacy behavior fallback for compatibility
                try:
                    timex = j["releases"][latest][0]["upload_time_iso_8601"]
                    x.timestamp = int(dt.timestamp(dt.strptime(timex, TIME_FORMAT_ISO)) * 1000)
                except (ValueError, KeyError, IndexError):
                    logging.warning("Couldn't parse timestamp, setting to 0.")
                    x.timestamp = 0

            # Previous release tracking for regression checks
            ordered_versions = _ordered_release_versions(releases if isinstance(releases, dict) else {})
            previous_version = None
            if selected_version in ordered_versions:
                idx = ordered_versions.index(selected_version)
                if idx > 0:
                    previous_version = ordered_versions[idx - 1]
            elif len(ordered_versions) >= 2:
                previous_version = ordered_versions[-2]
            x.previous_release_version = previous_version

            # Enrich with license metadata from PyPI info
            _enrich_with_license(x, j["info"])

            # Enrich with repository discovery and validation
            _enrich_with_repo(x, x.pkg_name, j["info"], selected_version)

            # Fetch weekly download stats (best-effort)
            x.weekly_downloads = _fetch_weekly_downloads(normalized)

            # Trust/provenance signals from Simple API (best effort)
            simple_json = _fetch_simple_index_json(normalized)
            cur_sig, cur_prov, cur_prov_url = _extract_simple_trust(simple_json, selected_version)
            prev_sig = prev_prov = None
            if previous_version:
                prev_sig, prev_prov, _ = _extract_simple_trust(simple_json, previous_version)

            # Fallback signature source from Warehouse JSON `has_sig`
            if cur_sig is None:
                cur_sig = _extract_legacy_json_signature(releases, selected_version)
            if previous_version and prev_sig is None:
                prev_sig = _extract_legacy_json_signature(releases, previous_version)

            x.registry_signature_present = cur_sig
            x.previous_registry_signature_present = prev_sig
            x.provenance_present = cur_prov
            x.previous_provenance_present = prev_prov
            x.provenance_url = cur_prov_url
            x.provenance_source = "pypi_simple_api"
            x.registry_signature_regressed = regressed(cur_sig, prev_sig)
            x.provenance_regressed = regressed(cur_prov, prev_prov)
            x.trust_score = score_from_boolean_signals([cur_sig, cur_prov])
            x.previous_trust_score = score_from_boolean_signals([prev_sig, prev_prov])
            delta, decreased = score_delta(x.trust_score, x.previous_trust_score)
            x.trust_score_delta = delta
            x.trust_score_decreased = decreased
        else:
            x.exists = False
