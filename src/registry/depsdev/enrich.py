"""deps.dev v3 enrichment: backfill MetaPackage fields and record provenance.

Backfills only when fields are missing; logs discrepancies when values differ.
Does not override existing fields unless strict=True is passed explicitly.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional, Tuple

from constants import Constants
from common.logging_utils import extra_context, is_debug_enabled, Timer
from registry.depsdev.client import DepsDevClient

# Use repository URL normalizer to ensure consistency with other enrichers
try:
    from src.repository.url_normalize import normalize_repo_url  # type: ignore
except Exception:  # pylint: disable=broad-exception-caught
    from repository.url_normalize import normalize_repo_url  # type: ignore

logger = logging.getLogger(__name__)


def _choose_license_from(data: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """Extract (license_id, spdx_expression?) from deps.dev-like JSON structures defensively.

    Fallback behavior:
    - If only an SPDX 'expression' is present (common in deps.dev), use it for both id and expression.
    """
    if not isinstance(data, dict):
        return None, None

    # Try common shapes first
    # 1) licenses: [{spdx_id|id|expression|license|name|type|key}, ...]
    licenses = data.get("licenses")
    if isinstance(licenses, list):
        for li in licenses:
            if not isinstance(li, dict):
                continue
            # prefer explicit SPDX id/name
            spdx = (
                li.get("spdx_id")
                or li.get("id")
                or li.get("identifier")
                or li.get("license")
                or li.get("name")
                or li.get("type")
                or li.get("key")
            )
            expr = li.get("expression") or li.get("spdx_expression") or li.get("spdx")
            if isinstance(spdx, str) and spdx.strip():
                return spdx.strip(), expr.strip() if isinstance(expr, str) and expr.strip() else None
            if isinstance(expr, str) and expr.strip():
                # Use SPDX expression as the license id when id is not provided
                val = expr.strip()
                return val, val

    # 2) license object {id|spdx_id|expression|name|type|key|spdx}
    lic = data.get("license")
    if isinstance(lic, dict):
        spdx = (
            lic.get("spdx_id")
            or lic.get("id")
            or lic.get("identifier")
            or lic.get("license")
            or lic.get("name")
            or lic.get("type")
            or lic.get("key")
        )
        expr = lic.get("expression") or lic.get("spdx_expression") or lic.get("spdx")
        if isinstance(spdx, str) and spdx.strip():
            return spdx.strip(), expr.strip() if isinstance(expr, str) and expr.strip() else None
        if isinstance(expr, str) and expr.strip():
            val = expr.strip()
            return val, val

    # 3) license string (fallback)
    if isinstance(lic, str) and lic.strip():
        return lic.strip(), None

    # 4) declaredLicenses style fallback (array of strings)
    declared = data.get("declaredLicenses") or data.get("declared_licenses")
    if isinstance(declared, list) and declared:
        first = next((s for s in declared if isinstance(s, str) and s.strip()), None)
        if first:
            v = first.strip()
            return v, v

    return None, None


def _choose_link(data: Dict[str, Any], keys: List[str]) -> Optional[str]:
    """Find a URL candidate from typical link shapes."""
    if not isinstance(data, dict):
        return None
    # links: {repo|source|repository|homepage: url}
    links = data.get("links") or data.get("url") or {}
    if isinstance(links, dict):
        for k in keys:
            v = links.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()

    # top-level fallbacks
    for k in keys:
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()

    # vcs/repository shapes
    vcs = data.get("vcs") or data.get("repository")
    if isinstance(vcs, dict):
        for k in ("url", "repo", "source"):
            v = vcs.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()

    return None


def _append_discrepancy(entry: Dict[str, Any], field: str, current: Any, new_val: Any, note: str) -> None:
    ds = entry.setdefault("discrepancies", [])
    if isinstance(ds, list):
        ds.append({"field": field, "current": current, "depsdev": new_val, "note": note})


def _merge_provenance(mp, dd_entry: Dict[str, Any]) -> None:
    """Merge depsdev provenance into package provenance."""
    prov = getattr(mp, "provenance", None) or {}
    # Keep existing depsdev block, extend it
    dd_prev = prov.get("depsdev", {})
    if isinstance(dd_prev, dict):
        # merge shallowly
        for k, v in dd_entry.items():
            if k == "fields":
                fields_prev = dd_prev.get("fields", {})
                if not isinstance(fields_prev, dict):
                    fields_prev = {}
                if isinstance(v, dict):
                    fields_prev.update(v)
                dd_prev["fields"] = fields_prev
            elif k == "discrepancies":
                prev_d = dd_prev.get("discrepancies", [])
                if not isinstance(prev_d, list):
                    prev_d = []
                if isinstance(v, list):
                    prev_d.extend(v)
                dd_prev["discrepancies"] = prev_d
            else:
                dd_prev[k] = v
        prov["depsdev"] = dd_prev
    else:
        prov["depsdev"] = dd_entry
    mp.provenance = prov


def enrich_metapackage(
    mp,
    ecosystem: str,
    name: str,
    version: Optional[str],
    client: Optional[DepsDevClient] = None,
    strict: Optional[bool] = None,
) -> None:
    """Backfill MetaPackage fields from deps.dev; record provenance and discrepancies.

    Args:
        mp: MetaPackage instance
        ecosystem: "npm" | "pypi" | "maven"
        name: package coordinates (npm name, pypi name normalized by client, or "group:artifact")
        version: concrete version string (optional)
        client: optional DepsDevClient (constructed if not provided)
        strict: when True, allow override of existing values; defaults to Constants.DEPSDEV_STRICT_OVERRIDE
    """
    if not getattr(Constants, "DEPSDEV_ENABLED", True):
        return

    _strict = bool(Constants.DEPSDEV_STRICT_OVERRIDE if strict is None else strict)
    try:
        with Timer() as t:
            if is_debug_enabled(logger):
                logger.debug(
                    "deps.dev enrichment start",
                    extra=extra_context(
                        event="depsdev_enrich_start",
                        component="depsdev_enrich",
                        ecosystem=ecosystem,
                        pkg=name,
                        version=version,
                    ),
                )
            c = client or DepsDevClient()
            project_status, project_headers, project_json = c.get_project(ecosystem, name)
            version_status, version_headers, version_json = (0, {}, None)
            if version:
                # Primary attempt with provided version
                version_status, version_headers, version_json = c.get_version(ecosystem, name, version)
                # Fallback: if non-200 or empty body, try lowercased variant (helps for some pre-release tags)
                if (not isinstance(version_json, dict) or not version_json) and (version_status != 200):
                    try:
                        v_lower = str(version).lower()
                    except Exception:  # pylint: disable=broad-exception-caught
                        v_lower = None
                    if v_lower and v_lower != version:
                        vs2, vh2, vj2 = c.get_version(ecosystem, name, v_lower)
                        if isinstance(vj2, dict) and vs2 == 200:
                            version_status, version_headers, version_json = vs2, vh2, vj2

            dd_prov: Dict[str, Any] = {
                "project_url": f"{c.base_url}/projects/{c._eco_value(ecosystem)}/{c.normalize_name(ecosystem, name)}",  # noqa: SLF001
                "version_url": (
                    f"{c.base_url}/versions/{c._eco_value(ecosystem)}/{c.normalize_name(ecosystem, name)}@{c.normalize_version(ecosystem, version)}"  # noqa: SLF001,E501
                    if version
                    else None
                ),
                "fetched_at_ts": int(time.time()),
                "fields": {},
                "discrepancies": [],
                "http": {
                    "project_status": project_status,
                    "version_status": version_status,
                },
            }

            # License backfill
            lic_id = None
            lic_expr = None
            if isinstance(version_json, dict):
                lic_id, lic_expr = _choose_license_from(version_json)
            if not lic_id and isinstance(project_json, dict):
                lic_id, lic_expr = _choose_license_from(project_json)

            current_lic = getattr(mp, "license_id", None)
            if lic_id:
                # Treat empty/whitespace license_id as missing for backfill purposes
                _cur_norm = (current_lic.strip() if isinstance(current_lic, str) else current_lic)
                _needs_backfill = (current_lic is None) or (isinstance(current_lic, str) and (_cur_norm == ""))
                if _needs_backfill:
                    # backfill
                    try:
                        setattr(mp, "license_id", lic_id)
                        setattr(mp, "license_source", "deps.dev")
                        setattr(mp, "license_available", True)
                        setattr(mp, "is_license_available", True)
                    except Exception:  # pylint: disable=broad-exception-caught
                        pass
                elif _cur_norm and _cur_norm != lic_id:
                    _append_discrepancy(dd_prov, "license_id", current_lic, lic_id, "deps.dev differing license")

                # Always record alternate
                dd_prov["fields"]["license"] = {"value": lic_id, "from": "deps.dev"}
                if lic_expr:
                    dd_prov["fields"]["license"]["expression"] = lic_expr

                # Debug: summarize license extraction and HTTP statuses
                if is_debug_enabled(logger):
                    try:
                        logger.debug(
                            "deps.dev license parse",
                            extra=extra_context(
                                event="depsdev_license",
                                component="depsdev_enrich",
                                ecosystem=ecosystem,
                                pkg=name,
                                version=version,
                                project_status=project_status,
                                version_status=version_status,
                                license_id=lic_id,
                            ),
                        )
                    except Exception:  # pylint: disable=broad-exception-caught
                        pass

            # Repository URL backfill (when not present)
            repo_url_candidate = None
            if isinstance(version_json, dict):
                repo_url_candidate = _choose_link(version_json, ["repo", "source", "repository"])
            if not repo_url_candidate and isinstance(project_json, dict):
                repo_url_candidate = _choose_link(project_json, ["repo", "source", "repository"])

            if repo_url_candidate:
                dd_prov["fields"]["repo_url_alt"] = repo_url_candidate
                if getattr(mp, "repo_url_normalized", None) is None:
                    try:
                        normalized = normalize_repo_url(repo_url_candidate)
                        if normalized and getattr(mp, "repo_url_normalized", None) is None:
                            mp.repo_url_normalized = normalized.normalized_url
                            if getattr(mp, "repo_host", None) is None and getattr(normalized, "host", None):
                                mp.repo_host = normalized.host
                    except Exception:  # pylint: disable=broad-exception-caught
                        # If normalization fails, still keep alternate in provenance
                        pass
                else:
                    # Existing repo differs? record discrepancy if materially different
                    try:
                        cur = getattr(mp, "repo_url_normalized", None)
                        if isinstance(cur, str) and cur and cur != repo_url_candidate:
                            _append_discrepancy(
                                dd_prov,
                                "repo_url_normalized",
                                cur,
                                repo_url_candidate,
                                "deps.dev provided alternate repository URL",
                            )
                    except Exception:  # pylint: disable=broad-exception-caught
                        pass

            # Homepage alternate (non-overriding)
            homepage = None
            if isinstance(version_json, dict):
                homepage = _choose_link(version_json, ["homepage"])
            if not homepage and isinstance(project_json, dict):
                homepage = _choose_link(project_json, ["homepage"])
            if homepage:
                dd_prov["fields"]["homepage_alt"] = homepage

            # Dependencies (record only in provenance)
            deps: List[Dict[str, Any]] = []
            for blob in (version_json, project_json):
                lst = (blob or {}).get("dependencies") if isinstance(blob, dict) else None
                if isinstance(lst, list):
                    for d in lst:
                        if not isinstance(d, dict):
                            continue
                        # Attempt to normalize fields; keep unknowns for visibility
                        deps.append(
                            {
                                "id": d.get("id") or d.get("purl") or d.get("name"),
                                "name": d.get("name"),
                                "version": d.get("version"),
                                "kind": d.get("relationType") or d.get("kind"),
                                "source": "deps.dev",
                            }
                        )
            # Deduplicate by tuple
            seen = set()
            uniq_deps = []
            for d in deps:
                key = (d.get("name"), d.get("version"), d.get("kind"))
                if key not in seen:
                    seen.add(key)
                    uniq_deps.append(d)
            if uniq_deps:
                dd_prov["fields"]["dependencies"] = uniq_deps

            # Vulnerabilities/advisories (provenance only)
            vulns: List[Dict[str, Any]] = []
            for blob in (version_json, project_json):
                vlist = (blob or {}).get("advisories") or (blob or {}).get("vulnerabilities")
                if isinstance(vlist, list):
                    for v in vlist:
                        if not isinstance(v, dict):
                            continue
                        vid = v.get("id") or v.get("osv_id") or v.get("ghsa_id")
                        vulns.append(
                            {
                                "id": vid,
                                "severity": v.get("severity"),
                                "url": v.get("url") or v.get("reference"),
                                "source": "deps.dev",
                            }
                        )
            # Dedupe by id
            vid_seen = set()
            uniq_v = []
            for v in vulns:
                key = v.get("id") or v.get("url")
                if key and key not in vid_seen:
                    vid_seen.add(key)
                    uniq_v.append(v)
            if uniq_v:
                dd_prov["fields"]["vulnerabilities"] = uniq_v

            # Merge provenance
            _merge_provenance(mp, dd_prov)

            if is_debug_enabled(logger):
                logger.debug(
                    "deps.dev enrichment completed",
                    extra=extra_context(
                        event="depsdev_enrich_complete",
                        component="depsdev_enrich",
                        outcome="success",
                        duration_ms=t.duration_ms(),
                        ecosystem=ecosystem,
                        pkg=name,
                        version=version,
                    ),
                )
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Never fail the pipeline due to deps.dev issues
        logger.warning(
            "deps.dev enrichment error",
            extra=extra_context(
                event="depsdev_error",
                component="depsdev_enrich",
                outcome="exception",
                message=str(exc),
                ecosystem=ecosystem,
                pkg=name,
                version=version,
            ),
        )
