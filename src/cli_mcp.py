"""MCP server for DepGate exposing dependency tools via the official MCP Python SDK.

This module implements a minimal MCP server with three tools:
  - Lookup_Latest_Version
  - Scan_Project
  - Scan_Dependency

Transport defaults to stdio JSON-RPC. If --host/--port are provided via CLI,
we'll run with streamable HTTP transport as a non-standard alternative.

Behavior is strictly aligned with existing DepGate logic and does not
introduce new finding types or semantics.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import argparse
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Tuple

from constants import Constants
from common.logging_utils import configure_logging as _configure_logging

# Import scan/registry wiring for reuse
from cli_build import (
    build_pkglist,
    create_metapackages,
    apply_version_resolution,
)
from cli_registry import check_against
from analysis.analysis_runner import run_analysis
from metapackage import MetaPackage as metapkg

# Version resolution service for fast lookups
try:
    from src.versioning.models import Ecosystem, PackageRequest, VersionSpec
    from src.versioning.service import VersionResolutionService
    from src.versioning.cache import TTLCache
    from src.versioning.parser import parse_manifest_entry
except ImportError:
    from versioning.models import Ecosystem, PackageRequest, VersionSpec
    from versioning.service import VersionResolutionService
    from versioning.cache import TTLCache
    from versioning.parser import parse_manifest_entry
_SHARED_TTL_CACHE = TTLCache()


# Official MCP SDK (FastMCP)
try:
    from mcp.server.fastmcp import FastMCP, Context  # type: ignore
except Exception as _imp_err:  # pragma: no cover - import error surfaced at runtime
    FastMCP = None  # type: ignore
    Context = object  # type: ignore


# ----------------------------
# Data models for structured I/O
# ----------------------------

@dataclass
class LookupLatestVersionInput:
    name: str
    ecosystem: Optional[str] = None  # npm|pypi|maven
    versionRange: Optional[str] = None
    registryUrl: Optional[str] = None
    projectDir: Optional[str] = None


@dataclass
class LookupLatestVersionOutput:
    name: str
    ecosystem: str
    latestVersion: Optional[str]
    satisfiesRange: Optional[bool]
    publishedAt: Optional[str]
    deprecated: Optional[bool]
    yanked: Optional[bool]
    license: Optional[str]
    registryUrl: Optional[str]
    repositoryUrl: Optional[str]
    cache: Dict[str, Any]


@dataclass
class ScanProjectInput:
    projectDir: str
    includeDevDependencies: Optional[bool] = None
    includeTransitive: Optional[bool] = None
    respectLockfiles: Optional[bool] = None
    offline: Optional[bool] = None
    strictProvenance: Optional[bool] = None
    paths: Optional[List[str]] = None
    analysisLevel: Optional[str] = None
    ecosystem: Optional[str] = None  # optional hint when multiple manifests exist


@dataclass
class ScanDependencyInput:
    name: str
    version: str
    ecosystem: str
    registryUrl: Optional[str] = None
    offline: Optional[bool] = None


def _eco_from_str(s: Optional[str]) -> Ecosystem:
    if not s:
        raise ValueError("ecosystem is required in this context")
    s = s.strip().lower()
    if s == "npm":
        return Ecosystem.NPM
    if s == "pypi":
        return Ecosystem.PYPI
    if s == "maven":
        return Ecosystem.MAVEN
    raise ValueError(f"unsupported ecosystem: {s}")


def _apply_registry_override(ecosystem: Ecosystem, registry_url: Optional[str]) -> None:
    if not registry_url:
        return
    if ecosystem == Ecosystem.NPM:
        try:
            setattr(Constants, "REGISTRY_URL_NPM", registry_url)
        except Exception:
            pass
    elif ecosystem == Ecosystem.PYPI:
        # Expect base ending with '/pypi/'; accept direct URL and append if needed
        val = registry_url if registry_url.endswith("/pypi/") else registry_url.rstrip("/") + "/pypi/"
        try:
            setattr(Constants, "REGISTRY_URL_PYPI", val)
        except Exception:
            pass
    elif ecosystem == Ecosystem.MAVEN:
        # For Maven, this impacts search endpoints elsewhere; version resolver reads metadata
        # directly from repo1.maven.org. For now, keep default; advanced registry selection
        # would require broader changes not in scope.
        pass


def _set_runtime_from_args(args) -> None:
    # Respect CLI overrides for logging/timeouts, without altering existing commands
    if getattr(args, "MCP_REQUEST_TIMEOUT", None):
        try:
            setattr(Constants, "REQUEST_TIMEOUT", int(args.MCP_REQUEST_TIMEOUT))
        except Exception:
            pass


def _sandbox_project_dir(project_dir: Optional[str], path: Optional[str]) -> None:
    if not project_dir or not path:
        return
    # Normalize and ensure the path is within project_dir
    root = os.path.abspath(project_dir)
    p = os.path.abspath(path)
    if not (p == root or p.startswith(root + os.sep)):
        raise PermissionError("Path outside of --project-dir sandbox")


def _reset_state() -> None:
    # Clean MetaPackage instances between tool invocations to avoid cross-talk
    try:
        metapkg.instances.clear()
    except Exception:
        pass


def _resolution_for(ecosystem: Ecosystem, name: str, range_spec: Optional[str]) -> Tuple[Optional[str], int, Optional[str], Dict[str, Any]]:
    svc = VersionResolutionService(_SHARED_TTL_CACHE)
    req = parse_manifest_entry(name, (str(range_spec).strip() if range_spec else None), ecosystem, "mcp")
    res = svc.resolve_all([req])
    rr = res.get((ecosystem, req.identifier))
    latest = rr.resolved_version if rr else None
    return latest, (rr.candidate_count if rr else 0), (rr.error if rr else None), {
        "fromCache": False,  # TTLCache does not expose hit flag
        "ageSeconds": None,
    }


def _build_cli_args_for_project_scan(inp: ScanProjectInput) -> Any:
    args = argparse.Namespace()
    # Map into existing CLI surfaces used by build_pkglist/create_metapackages
    if inp.ecosystem:
        pkg_type = inp.ecosystem
    else:
        # Infer: prefer npm if package.json exists, else pypi via requirements.txt/pyproject, else maven by pom.xml
        root = inp.projectDir
        if os.path.isfile(os.path.join(root, Constants.PACKAGE_JSON_FILE)):
            pkg_type = "npm"
        elif os.path.isfile(os.path.join(root, Constants.REQUIREMENTS_FILE)) or os.path.isfile(
            os.path.join(root, Constants.PYPROJECT_TOML_FILE)
        ):
            pkg_type = "pypi"
        elif os.path.isfile(os.path.join(root, Constants.POM_XML_FILE)):
            pkg_type = "maven"
        else:
            # Default to npm to preserve common behavior
            pkg_type = "npm"
    args.package_type = pkg_type
    args.LIST_FROM_FILE = []
    args.FROM_SRC = [inp.projectDir]
    args.SINGLE = None
    args.RECURSIVE = False
    args.LEVEL = inp.analysisLevel or "compare"
    args.OUTPUT = None
    args.OUTPUT_FORMAT = None
    args.LOG_LEVEL = "INFO"
    args.LOG_FILE = None
    args.ERROR_ON_WARNINGS = False
    args.QUIET = True
    # deps.dev defaults (allow overrides via env handled elsewhere)
    args.DEPSDEV_DISABLE = not Constants.DEPSDEV_ENABLED
    args.DEPSDEV_BASE_URL = Constants.DEPSDEV_BASE_URL
    args.DEPSDEV_CACHE_TTL = Constants.DEPSDEV_CACHE_TTL_SEC
    args.DEPSDEV_MAX_CONCURRENCY = Constants.DEPSDEV_MAX_CONCURRENCY
    args.DEPSDEV_MAX_RESPONSE_BYTES = Constants.DEPSDEV_MAX_RESPONSE_BYTES
    args.DEPSDEV_STRICT_OVERRIDE = Constants.DEPSDEV_STRICT_OVERRIDE
    return args


def _gather_results() -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "packages": [],
        "findings": [],
        "summary": {},
    }
    pkgs = []
    for mp in metapkg.instances:
        pkgs.append(
            {
                "name": getattr(mp, "pkg_name", None),
                "ecosystem": getattr(mp, "pkg_type", None),
                "version": getattr(mp, "resolved_version", None),
                "repositoryUrl": getattr(mp, "repo_url_normalized", None),
                "license": getattr(mp, "license_id", None),
                "linked": getattr(mp, "linked", None),
                "repoVersionMatch": getattr(mp, "repo_version_match", None),
                "policyDecision": getattr(mp, "policy_decision", None),
            }
        )
    out["packages"] = pkgs
    # findings and summary are inferred by callers today; we include minimal fields
    out["summary"] = {
        "count": len(pkgs),
    }
    return out


def run_mcp_server(args) -> None:
    # Configure logging first
    _configure_logging()
    try:
        level_name = str(getattr(args, "LOG_LEVEL", "INFO")).upper()
        level_value = getattr(logging, level_name, logging.INFO)
        logging.getLogger().setLevel(level_value)
    except Exception:
        pass

    _set_runtime_from_args(args)

    server_name = "depgate-mcp"
    server_version = str(getattr(sys.modules.get("depgate"), "__version__", "")) or ""  # best-effort
    if FastMCP is None:
        sys.stderr.write("MCP server not available: 'mcp' package is not installed.\n")
        sys.exit(1)
    # Default sandbox root to current working directory if not provided
    if not getattr(args, "MCP_PROJECT_DIR", None):
        try:
            setattr(args, "MCP_PROJECT_DIR", os.getcwd())
        except Exception:
            pass
    mcp = FastMCP(server_name)

    @mcp.tool(title="Lookup Latest Version", name="Lookup_Latest_Version")
    def lookup_latest_version(
        name: str,
        ecosystem: Optional[str] = None,
        versionRange: Optional[str] = None,
        registryUrl: Optional[str] = None,
        projectDir: Optional[str] = None,
        ctx: Any = None,
    ) -> Dict[str, Any]:
        """Fast lookup of the latest stable version using DepGate's resolvers and caching."""
        # Validate input
        try:
            from mcp_schemas import LOOKUP_LATEST_VERSION_INPUT, LOOKUP_LATEST_VERSION_OUTPUT  # type: ignore
            from mcp_validate import validate_input, safe_validate_output  # type: ignore
            validate_input(
                LOOKUP_LATEST_VERSION_INPUT,
                {
                    "name": name,
                    "ecosystem": ecosystem,
                    "versionRange": versionRange,
                    "registryUrl": registryUrl,
                    "projectDir": projectDir,
                },
            )
        except Exception as se:  # pragma: no cover - validation failure
            if "Invalid input" in str(se):
                raise RuntimeError(str(se))
            # Otherwise, continue best-effort
        # Offline/no-network enforcement
        if getattr(args, "MCP_NO_NETWORK", False) or getattr(args, "MCP_OFFLINE", False):
            # Version resolvers use HTTP; fail fast in offline modes
            raise RuntimeError("offline: registry access disabled")

        eco = _eco_from_str(ecosystem) if ecosystem else Ecosystem.NPM
        if projectDir and args.MCP_PROJECT_DIR:
            _sandbox_project_dir(args.MCP_PROJECT_DIR, projectDir)

        _apply_registry_override(eco, registryUrl)

        latest, candidate_count, err, cache_info = _resolution_for(eco, name, versionRange)

        # Optional metadata enrichment (no new analysis types; best-effort)
        published_at: Optional[str] = None
        deprecated: Optional[bool] = None
        yanked: Optional[bool] = None
        license_id: Optional[str] = None
        repo_url: Optional[str] = None

        try:
            if latest:
                if eco == Ecosystem.NPM:
                    from common.http_client import get_json as _get_json
                    import urllib.parse as _u
                    url = f"{Constants.REGISTRY_URL_NPM}{_u.quote(name, safe='')}"
                    status, _, data = _get_json(url)
                    if status == 200 and isinstance(data, dict):
                        times = (data or {}).get("time", {}) or {}
                        published_at = times.get(latest)
                        ver_meta = ((data or {}).get("versions", {}) or {}).get(latest, {}) or {}
                        deprecated = bool(ver_meta.get("deprecated")) if ("deprecated" in ver_meta) else None
                        lic = ver_meta.get("license") or (data or {}).get("license")
                        license_id = str(lic) if lic else None
                        repo = (ver_meta.get("repository") or (data or {}).get("repository") or {})
                        if isinstance(repo, dict):
                            repo_url = repo.get("url")
                        elif isinstance(repo, str):
                            repo_url = repo
                elif eco == Ecosystem.PYPI:
                    from common.http_client import get_json as _get_json
                    url = f"{Constants.REGISTRY_URL_PYPI}{name}/json"
                    status, _, data = _get_json(url)
                    if status == 200 and isinstance(data, dict):
                        info = (data or {}).get("info", {}) or {}
                        license_id = info.get("license") or None
                        # Repo URL heuristic from project_urls
                        proj_urls = info.get("project_urls") or {}
                        if isinstance(proj_urls, dict):
                            repo_url = (
                                proj_urls.get("Source")
                                or proj_urls.get("Source Code")
                                or proj_urls.get("Homepage")
                                or None
                            )
                        # Release publish/yanked
                        rels = (data or {}).get("releases", {}) or {}
                        files = rels.get(latest) or []
                        # publishedAt: prefer first file's upload_time_iso_8601
                        if files and isinstance(files, list):
                            published_at = files[0].get("upload_time_iso_8601")
                            yanked = any(bool(f.get("yanked")) for f in files)
                # Maven metadata lacks license/publish at the resolver stage; skip
        except Exception:
            # Best-effort; leave fields as None
            pass
        out = {
            "name": name,
            "ecosystem": eco.value,
            "latestVersion": latest,
            "satisfiesRange": None,
            "publishedAt": published_at,
            "deprecated": deprecated,
            "yanked": yanked,
            "license": license_id,
            "registryUrl": registryUrl,
            "repositoryUrl": repo_url,
            "cache": cache_info,
            "_candidates": candidate_count,
        }
        try:
            # Validate output best-effort
            safe_validate_output(LOOKUP_LATEST_VERSION_OUTPUT, out)  # type: ignore
        except Exception:
            pass
        if versionRange and latest:
            # conservative: declare satisfiesRange True if resolved latest equals range when exact
            out["satisfiesRange"] = True if versionRange.strip() == latest else None
        if err:
            # propagate as error via FastMCP structured result – clients will surface call error content
            raise RuntimeError(err)
        return out

    @mcp.tool(title="Scan Project", name="Scan_Project")
    def scan_project(
        projectDir: str,
        includeDevDependencies: Optional[bool] = None,
        includeTransitive: Optional[bool] = None,
        respectLockfiles: Optional[bool] = None,
        offline: Optional[bool] = None,
        strictProvenance: Optional[bool] = None,
        paths: Optional[List[str]] = None,
        analysisLevel: Optional[str] = None,
        ecosystem: Optional[str] = None,
        ctx: Any = None,
        ) -> Dict[str, Any]:
        # Validate input
        try:
            from mcp_schemas import SCAN_PROJECT_INPUT  # type: ignore
            from mcp_validate import validate_input  # type: ignore
            validate_input(
                SCAN_PROJECT_INPUT,
                {
                    "projectDir": projectDir,
                    "includeDevDependencies": includeDevDependencies,
                    "includeTransitive": includeTransitive,
                    "respectLockfiles": respectLockfiles,
                    "offline": offline,
                    "strictProvenance": strictProvenance,
                    "paths": paths,
                    "analysisLevel": analysisLevel,
                    "ecosystem": ecosystem,
                },
            )
        except Exception as se:  # pragma: no cover
            if "Invalid input" in str(se):
                raise RuntimeError(str(se))
        if args.MCP_PROJECT_DIR:
            _sandbox_project_dir(args.MCP_PROJECT_DIR, projectDir)
        if getattr(args, "MCP_NO_NETWORK", False) or (offline is True) or getattr(args, "MCP_OFFLINE", False):
            # For now, scanning requires network for registry enrichment
            raise RuntimeError("offline: networked scan not permitted")

        _reset_state()
        inp = ScanProjectInput(
            projectDir=projectDir,
            includeDevDependencies=includeDevDependencies,
            includeTransitive=includeTransitive,
            respectLockfiles=respectLockfiles,
            offline=offline,
            strictProvenance=strictProvenance,
            paths=paths,
            analysisLevel=analysisLevel,
            ecosystem=ecosystem,
        )
        scan_args = _build_cli_args_for_project_scan(inp)

        # Build and execute pipeline identically to CLI scan
        pkglist = build_pkglist(scan_args)
        create_metapackages(scan_args, pkglist)
        apply_version_resolution(scan_args, pkglist)
        check_against(scan_args.package_type, scan_args.LEVEL, metapkg.instances)
        run_analysis(scan_args.LEVEL, scan_args, metapkg.instances)
        result = _gather_results()
        # Strictly validate shape; surface issues as tool errors
        try:
            from mcp_schemas import SCAN_RESULTS_OUTPUT  # type: ignore
            from mcp_validate import validate_output  # type: ignore
            validate_output(SCAN_RESULTS_OUTPUT, result)
        except Exception as se:
            raise RuntimeError(str(se))
        return result

    @mcp.tool(title="Scan Dependency", name="Scan_Dependency")
    def scan_dependency(
        name: str,
        version: str,
        ecosystem: str,
        registryUrl: Optional[str] = None,
        offline: Optional[bool] = None,
        ctx: Any = None,
        ) -> Dict[str, Any]:
        # Validate input
        try:
            from mcp_schemas import SCAN_DEPENDENCY_INPUT  # type: ignore
            from mcp_validate import validate_input  # type: ignore
            validate_input(
                SCAN_DEPENDENCY_INPUT,
                {
                    "name": name,
                    "version": version,
                    "ecosystem": ecosystem,
                    "registryUrl": registryUrl,
                    "offline": offline,
                },
            )
        except Exception as se:  # pragma: no cover
            if "Invalid input" in str(se):
                raise RuntimeError(str(se))
        if getattr(args, "MCP_NO_NETWORK", False) or (offline is True) or getattr(args, "MCP_OFFLINE", False):
            raise RuntimeError("offline: networked scan not permitted")

        eco = _eco_from_str(ecosystem)
        _apply_registry_override(eco, registryUrl)

        _reset_state()
        # Build a minimal args facade to reuse pipeline like single-token scan
        scan_args = argparse.Namespace()
        scan_args.package_type = eco.value
        scan_args.LIST_FROM_FILE = []
        scan_args.FROM_SRC = None
        scan_args.SINGLE = [name]
        scan_args.RECURSIVE = False
        scan_args.LEVEL = "compare"
        scan_args.OUTPUT = None
        scan_args.OUTPUT_FORMAT = None
        scan_args.LOG_LEVEL = "INFO"
        scan_args.LOG_FILE = None
        scan_args.ERROR_ON_WARNINGS = False
        scan_args.QUIET = True
        scan_args.DEPSDEV_DISABLE = not Constants.DEPSDEV_ENABLED
        scan_args.DEPSDEV_BASE_URL = Constants.DEPSDEV_BASE_URL
        scan_args.DEPSDEV_CACHE_TTL = Constants.DEPSDEV_CACHE_TTL_SEC
        scan_args.DEPSDEV_MAX_CONCURRENCY = Constants.DEPSDEV_MAX_CONCURRENCY
        scan_args.DEPSDEV_MAX_RESPONSE_BYTES = Constants.DEPSDEV_MAX_RESPONSE_BYTES
        scan_args.DEPSDEV_STRICT_OVERRIDE = Constants.DEPSDEV_STRICT_OVERRIDE

        pkglist = build_pkglist(scan_args)
        create_metapackages(scan_args, pkglist)
        # Force requested spec to exact version for metapackages before resolution
        try:
            for mp in metapkg.instances:
                mp._requested_spec = version  # internal field
        except Exception:
            pass
        apply_version_resolution(scan_args, pkglist)
        check_against(scan_args.package_type, scan_args.LEVEL, metapkg.instances)
        run_analysis(scan_args.LEVEL, scan_args, metapkg.instances)
        result = _gather_results()
        try:
            from mcp_schemas import SCAN_RESULTS_OUTPUT  # type: ignore
            from mcp_validate import validate_output  # type: ignore
            validate_output(SCAN_RESULTS_OUTPUT, result)
        except Exception as se:
            raise RuntimeError(str(se))
        return result

    # Start server
    host = getattr(args, "MCP_HOST", None)
    port = getattr(args, "MCP_PORT", None)
    if host and port:
        # Non-standard/custom for this repo: expose streamable HTTP for testing tools
        mcp.settings.host = host
        try:
            mcp.settings.port = int(port)
        except Exception:
            pass
        mcp.run(transport="streamable-http")
    else:
        mcp.run()  # defaults to stdio
