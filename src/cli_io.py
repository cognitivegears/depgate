"""CLI I/O utilities for DepGate: file loading and JSON/CSV exports."""

import csv
import json
import logging
import sys

from constants import ExitCodes


def load_pkgs_file(file_name):
    """Loads the packages from a file.

    Args:
        file_name (str): File path containing the list of packages.

    Raises:
        TypeError: If the input list cannot be processed

    Returns:
        list: List of packages
    """
    try:
        with open(file_name, encoding='utf-8') as file:
            return [line.strip() for line in file]
    except FileNotFoundError as e:
        logging.error("File not found: %s, aborting", e)
        sys.exit(ExitCodes.FILE_ERROR.value)
    except IOError as e:
        logging.error("IO error: %s, aborting", e)
        sys.exit(ExitCodes.FILE_ERROR.value)


def export_csv(instances, path):
    """Exports the package properties to a CSV file.

    Args:
        instances (list): List of package instances.
        path (str): File path to export the CSV.
    """
    headers = [
        "Package Name",
        "Package Type",
        "Exists on External",
        "Org/Group ID",
        "Score",
        "Version Count",
        "Timestamp",
        "Risk: Missing",
        "Risk: Low Score",
        "Risk: Min Versions",
        "Risk: Too New",
        "Risk: Any Risks",
        # Append new fields before repo_* to preserve last-five repo_* columns for compatibility
        "requested_spec",
        "resolved_version",
        "resolution_mode",
        "dependency_relation",
        "dependency_requirement",
        "dependency_scope",
        "repo_stars",
        "repo_contributors",
        "repo_last_activity",
        "repo_present_in_registry",
        "repo_version_match",
    ]
    rows = [headers]

    def _nv(v):
        return "" if v is None else v

    for x in instances:
        # Build row aligned to headers; do NOT include policy/license columns here to preserve legacy CSV shape
        row = [
            x.pkg_name,
            x.pkg_type,
            x.exists,
            x.org_id,
            x.score,
            x.version_count,
            x.timestamp,
            x.risk_missing,
            x.risk_low_score,
            x.risk_min_versions,
            x.risk_too_new,
            x.has_risk(),
            _nv(getattr(x, "requested_spec", None)),
            _nv(getattr(x, "resolved_version", None)),
            _nv(getattr(x, "resolution_mode", None)),
            _nv(getattr(x, "dependency_relation", None)),
            _nv(getattr(x, "dependency_requirement", None)),
            _nv(getattr(x, "dependency_scope", None)),
            _nv(getattr(x, "repo_stars", None)),
            _nv(getattr(x, "repo_contributors", None)),
            _nv(getattr(x, "repo_last_activity_at", None)),
        ]
        # repo_present_in_registry with special-case blanking
        _present = getattr(x, "repo_present_in_registry", None)
        _norm_url = getattr(x, "repo_url_normalized", None)
        if (_present is False) and (_norm_url is None):
            row.append("")
        else:
            row.append(_nv(_present))
        # repo_version_match simplified to boolean 'matched' or blank
        _ver_match = getattr(x, "repo_version_match", None)
        if _ver_match is None:
            row.append("")
        else:
            try:
                row.append(bool(_ver_match.get("matched")))
            except Exception:  # pylint: disable=broad-exception-caught
                row.append("")
        rows.append(row)
    try:
        with open(path, 'w', newline='', encoding='utf-8') as file:
            export = csv.writer(file)
            export.writerows(rows)
        logging.info("CSV file has been successfully exported at: %s", path)
    except (OSError, csv.Error) as e:
        logging.error("CSV file couldn't be written to disk: %s", e)
        sys.exit(1)


def export_json(instances, path):
    """Exports the package properties to a JSON file.

    Args:
        instances (list): List of package instances.
        path (str): File path to export the JSON.
    """
    data = []
    for x in instances:
        entry = {
            "packageName": x.pkg_name,
            "orgId": x.org_id,
            "packageType": x.pkg_type,
            "exists": x.exists,
            "score": x.score,
            "versionCount": x.version_count,
            "createdTimestamp": x.timestamp,
            "repo_stars": x.repo_stars,
            "repo_contributors": x.repo_contributors,
            "repo_last_activity": x.repo_last_activity_at,
            "repo_present_in_registry": (
                None
                if (
                    getattr(x, "repo_url_normalized", None) is None
                    and x.repo_present_in_registry is False
                )
                else x.repo_present_in_registry
            ),
            "repo_version_match": x.repo_version_match,
            "risk": {
                "hasRisk": x.has_risk(),
                "isMissing": x.risk_missing,
                "hasLowScore": x.risk_low_score,
                "minVersions": x.risk_min_versions,
                "isNew": x.risk_too_new
            },
            "requested_spec": getattr(x, "requested_spec", None),
            "resolved_version": getattr(x, "resolved_version", None),
            "resolution_mode": getattr(x, "resolution_mode", None),
            "dependency_relation": getattr(x, "dependency_relation", None),
            "dependency_requirement": getattr(x, "dependency_requirement", None),
            "dependency_scope": getattr(x, "dependency_scope", None),
            "policy": {
                "decision": getattr(x, "policy_decision", None),
                "violated_rules": getattr(x, "policy_violated_rules", []),
                "evaluated_metrics": getattr(x, "policy_evaluated_metrics", {}),
            },
            "license": {
                "id": getattr(x, "license_id", None),
                "available": getattr(x, "license_available", None),
                "source": getattr(x, "license_source", None),
            }
        }
        # Conditionally include linked-analysis fields without altering legacy outputs
        if getattr(x, "_linked_mode", False):
            entry["repositoryUrl"] = getattr(x, "repo_url_normalized", None)
            entry["tagMatch"] = bool(getattr(x, "_linked_tag_match", False))
            entry["releaseMatch"] = bool(getattr(x, "_linked_release_match", False))
            entry["linked"] = bool(getattr(x, "linked", False))
        data.append(entry)
    try:
        with open(path, 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
        logging.info("JSON file has been successfully exported at: %s", path)
    except OSError as e:
        logging.error("JSON file couldn't be written to disk: %s", e)
        sys.exit(1)


def print_banner() -> None:
    """Print the DepGate banner."""
    logging.info(r"""
┬─┐ ┬─┐ ┬─┐ ┌─┐ ┬─┐ ┌┐┐ ┬─┐
│ │ │─  │─┘ │ ┬ │─┤  │  │─
──┘ ┴─┘ ┴   │─┘ ┘ │  ┘  ┴─┘

  Dependency Supply-Chain/Confusion Risk Checker
""")
