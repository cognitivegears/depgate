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
import logging
import os
import sys
import argparse
from typing import Any, Dict, List, Optional, Tuple
from typing_extensions import TypedDict

import urllib.parse as _u
from constants import Constants
from common.logging_utils import configure_logging as _configure_logging
from common.http_client import get_json as _get_json

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
    from src.versioning.models import Ecosystem
    from src.versioning.service import VersionResolutionService
    from src.versioning.cache import TTLCache
    from src.versioning.parser import parse_manifest_entry
except ImportError:
    from versioning.models import Ecosystem
    from versioning.service import VersionResolutionService
    from versioning.cache import TTLCache
    from versioning.parser import parse_manifest_entry
_SHARED_TTL_CACHE = TTLCache()


# Official MCP SDK (FastMCP)
try:
    from mcp.server.fastmcp import FastMCP  # type: ignore
except ImportError:  # pragma: no cover - import error surfaced at runtime
    # MCP SDK not available; gracefully degrade by setting FastMCP to None
    # The run_mcp_server function will check and exit with error message if needed
    FastMCP = None  # type: ignore


# ----------------------------
# Helpers and internal handlers
# ----------------------------


class PackageOut(TypedDict, total=False):
    name: Optional[str]
    ecosystem: Optional[str]
    version: Optional[str]
    repositoryUrl: Optional[str]
    license: Optional[str]
    linked: Optional[bool]
    repoVersionMatch: Any
    policyDecision: Any


class SummaryOut(TypedDict):
    count: int


class ScanResultOut(TypedDict, total=False):
    packages: List[PackageOut]
    findings: List[Dict[str, Any]]
    summary: SummaryOut


class LookupOut(TypedDict, total=False):
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
    candidates: int


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
        except AttributeError:
            pass
    elif ecosystem == Ecosystem.PYPI:
        # Expect base ending with '/pypi/'; accept direct URL and append if needed
        val = registry_url if registry_url.endswith("/pypi/") else registry_url.rstrip("/") + "/pypi/"
        try:
            setattr(Constants, "REGISTRY_URL_PYPI", val)
        except AttributeError:
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
        except (ValueError, TypeError, AttributeError):
            pass


def _sandbox_project_dir(project_dir: Optional[str], path: Optional[str]) -> None:
    if not project_dir or not path:
        return
    # Normalize and ensure the path is within project_dir
    root = os.path.abspath(project_dir)
    p = os.path.abspath(path)
    if not (p == root or p.startswith(root + os.sep)):
        raise PermissionError("Path outside of --project-dir sandbox")


def _require_online(args: Any, offline_flag: Optional[bool]) -> None:
    """Raise if online access is disabled by flags."""
    if getattr(args, "MCP_NO_NETWORK", False) or (offline_flag is True) or getattr(args, "MCP_OFFLINE", False):
        raise RuntimeError("offline: networked scan not permitted")


def _reset_state() -> None:
    # Clean MetaPackage instances between tool invocations to avoid cross-talk
    try:
        metapkg.instances.clear()
    except AttributeError:
        # If instances is not a list/collection, ignore (defensive programming)
        pass


def _resolution_for(
    ecosystem: Ecosystem,
    name: str,
    range_spec: Optional[str],
) -> Tuple[
    Optional[str], int, Optional[str], Dict[str, Any]
]:
    """Resolve the latest version for a package in the given ecosystem.

    Args:
        ecosystem: The package ecosystem (npm, pypi, maven).
        name: The package name.
        range_spec: Optional version range specification (e.g., "^1.0.0", ">=2.0.0").

    Returns:
        Tuple containing:
            - resolved_version (Optional[str]): The resolved latest version string, or None if resolution failed.
            - candidate_count (int): The number of candidate versions found in the registry.
            - error_message (Optional[str]): Error message if resolution failed, None otherwise.
            - cache_metadata (Dict[str, Any]): Cache-related metadata (fromCache, ageSeconds).
    """
    svc = VersionResolutionService(_SHARED_TTL_CACHE)
    req = parse_manifest_entry(name, (str(range_spec).strip() if range_spec else None), ecosystem, "mcp")
    res = svc.resolve_all([req])
    rr = res.get((ecosystem, req.identifier))
    latest = rr.resolved_version if rr else None
    return latest, (rr.candidate_count if rr else 0), (rr.error if rr else None), {
        "fromCache": False,  # TTLCache does not expose hit flag
        "ageSeconds": None,
    }


def _validate(schema_name: str, data: Dict[str, Any]) -> None:
    """Validate input payload against a named schema from depgate_mcp.schemas."""
    try:
        from depgate_mcp.schemas import (  # type: ignore
            LOOKUP_LATEST_VERSION_INPUT,
            SCAN_PROJECT_INPUT,
            SCAN_DEPENDENCY_INPUT,
        )
        from depgate_mcp.validate import validate_input as _validate_input  # type: ignore
        from depgate_mcp.validate import SchemaError  # type: ignore
        mapping = {
            "lookup": LOOKUP_LATEST_VERSION_INPUT,
            "project": SCAN_PROJECT_INPUT,
            "dependency": SCAN_DEPENDENCY_INPUT,
        }
        schema = mapping[schema_name]
        _validate_input(schema, data)
    except SchemaError as se:
        # Re-raise schema validation errors as RuntimeError for consistency
        raise RuntimeError(str(se)) from se
    except KeyError as ke:
        # Unknown schema name
        raise RuntimeError(f"Unknown schema name: {schema_name}") from ke
    except Exception as se:  # pragma: no cover
        # Unexpected errors during validation setup (e.g., import failures)
        # Only re-raise if it looks like a validation error
        if "Invalid input" in str(se):
            raise RuntimeError(str(se)) from se


def _validate_output_strict(result: Dict[str, Any]) -> None:
    """Validate scan result output strictly."""
    from depgate_mcp.schemas import SCAN_RESULTS_OUTPUT  # type: ignore
    from depgate_mcp.validate import validate_output as _validate_output  # type: ignore
    _validate_output(SCAN_RESULTS_OUTPUT, result)


def _safe_validate_lookup_output(out: Dict[str, Any]) -> None:
    """Best-effort validation for lookup output; ignore failures."""
    try:
        from depgate_mcp.schemas import LOOKUP_LATEST_VERSION_OUTPUT  # type: ignore
        from depgate_mcp.validate import safe_validate_output as _safe  # type: ignore
        _safe(LOOKUP_LATEST_VERSION_OUTPUT, out)
    except Exception:
        # Best-effort validation: ignore any validation errors to avoid breaking tool replies
        pass


def _enrich_lookup_metadata(eco: Ecosystem, name: str, latest: Optional[str]) -> Dict[str, Any]:
    """Fetch lightweight metadata for the latest version when available."""
    published_at: Optional[str] = None
    deprecated: Optional[bool] = None
    yanked: Optional[bool] = None
    license_id: Optional[str] = None
    repo_url: Optional[str] = None

    if not latest:
        return {
            "published_at": None,
            "deprecated": None,
            "yanked": None,
            "license_id": None,
            "repo_url": None,
        }

    # Skip HTTP calls in test mode to avoid hangs
    if os.environ.get("FAKE_REGISTRY", "0") == "1":
        return {
            "published_at": None,
            "deprecated": None,
            "yanked": None,
            "license_id": None,
            "repo_url": None,
        }

    if eco == Ecosystem.NPM:
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
        url = f"{Constants.REGISTRY_URL_PYPI}{name}/json"
        status, _, data = _get_json(url)
        if status == 200 and isinstance(data, dict):
            info = (data or {}).get("info", {}) or {}
            license_id = info.get("license") or None
            proj_urls = info.get("project_urls") or {}
            if isinstance(proj_urls, dict):
                repo_url = (
                    proj_urls.get("Source")
                    or proj_urls.get("Source Code")
                    or proj_urls.get("Homepage")
                    or None
                )
            rels = (data or {}).get("releases", {}) or {}
            files = rels.get(latest) or []
            if files and isinstance(files, list):
                published_at = files[0].get("upload_time_iso_8601")
                yanked = any(bool(f.get("yanked")) for f in files)
    return {
        "published_at": published_at,
        "deprecated": deprecated,
        "yanked": yanked,
        "license_id": license_id,
        "repo_url": repo_url,
    }


def _handle_lookup_latest_version(
    *,
    name: str,
    eco: Ecosystem,
    version_range: Optional[str],
    registry_url: Optional[str],
) -> Dict[str, Any]:
    """Core logic for lookup tool; assumes sandbox/online checks already done."""
    _apply_registry_override(eco, registry_url)

    res = _resolution_for(eco, name, version_range)
    meta = _enrich_lookup_metadata(eco, name, res[0])
    result = {
        "name": name,
        "ecosystem": eco.value,
        "latestVersion": res[0],
        "satisfiesRange": (version_range.strip() == res[0]) if (version_range and res[0]) else None,
        "publishedAt": meta["published_at"],
        "deprecated": meta["deprecated"],
        "yanked": meta["yanked"],
        "license": meta["license_id"],
        "registryUrl": registry_url,
        "repositoryUrl": meta["repo_url"],
        "cache": res[3],
        "candidates": res[1],
    }
    _safe_validate_lookup_output(result)
    if res[2]:
        raise RuntimeError(res[2])
    return result


def _run_scan_pipeline(scan_args: Any) -> Dict[str, Any]:
    pkglist = build_pkglist(scan_args)
    create_metapackages(scan_args, pkglist)
    apply_version_resolution(scan_args, pkglist)
    check_against(scan_args.package_type, scan_args.LEVEL, metapkg.instances)
    run_analysis(scan_args.LEVEL, scan_args, metapkg.instances)
    return _gather_results()


def _build_args_for_single_dependency(eco: Ecosystem, name: str, version: Optional[str] = None) -> Any:
    """Construct scan args for a single dependency token."""
    scan_args = argparse.Namespace()
    scan_args.package_type = eco.value
    scan_args.LIST_FROM_FILE = []
    scan_args.FROM_SRC = None
    # Include version in token if provided (format: name:version for parse_cli_token)
    if version:
        scan_args.SINGLE = [f"{name}:{version}"]
    else:
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
    return scan_args


def _build_cli_args_for_project_scan(
    project_dir: str,
    ecosystem_hint: Optional[str],
    analysis_level: Optional[str],
) -> Any:
    args = argparse.Namespace()
    # Map into existing CLI surfaces used by build_pkglist/create_metapackages
    if ecosystem_hint:
        pkg_type = ecosystem_hint
    else:
        # Infer: prefer npm if package.json exists, else pypi via requirements.txt/pyproject, else maven by pom.xml
        root = project_dir
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
    args.FROM_SRC = [project_dir]
    args.SINGLE = None
    args.RECURSIVE = False
    args.LEVEL = analysis_level or "compare"
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


def _setup_log_level(args: Any) -> None:
    """Apply LOG_LEVEL from args defensively without raising."""
    try:
        level_name = str(getattr(args, "LOG_LEVEL", "INFO")).upper()
        level_value = getattr(logging, level_name, logging.INFO)
        logging.getLogger().setLevel(level_value)
    except Exception:  # pylint: disable=broad-exception-caught
        # Defensive: never break CLI on logging setup
        pass


def run_mcp_server(args) -> None:
    """Entry point for launching the MCP server (stdio or streamable-http)."""
    # Configure logging and runtime
    _configure_logging()
    _setup_log_level(args)
    _set_runtime_from_args(args)

    server_name = "depgate-mcp"
    if FastMCP is None:
        sys.stderr.write("MCP server not available: 'mcp' package is not installed.\n")
        sys.exit(1)
    # FastMCP is guaranteed to be non-None here due to the check above
    # Type narrowing: after the None check and early exit, FastMCP must be callable
    assert FastMCP is not None
    _FastMCP = FastMCP  # Assign to local variable for type narrowing
    class DepGateMCP(_FastMCP):  # type: ignore
        async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any] | List[Any]:  # type: ignore[override]
            # Use FastMCP's conversion, then flatten to pure structured dict when available
            context = self.get_context()
            raw = await self._tool_manager.call_tool(name, arguments, context=context, convert_result=True)
            # raw can be Sequence[ContentBlock] or (Sequence[ContentBlock], dict)
            if isinstance(raw, tuple) and len(raw) == 2 and isinstance(raw[1], dict):
                structured = raw[1]
                # FastMCP may return structuredContent nested - extract it if present
                if isinstance(structured, dict) and "structuredContent" in structured:
                    return structured["structuredContent"]
                return structured
            # If raw is a dict with structuredContent, extract it
            if isinstance(raw, dict) and "structuredContent" in raw:
                return raw["structuredContent"]
            return raw  # type: ignore[return-value]

    mcp = DepGateMCP(server_name)

    @mcp.tool(title="Lookup Latest Version", name="Lookup_Latest_Version", structured_output=True)
    def lookup_latest_version(  # pylint: disable=invalid-name,too-many-arguments
        name: str,
        ecosystem: Optional[str] = None,
        versionRange: Optional[str] = None,
        registryUrl: Optional[str] = None,
        projectDir: Optional[str] = None,
        ctx: Any = None,
    ) -> LookupOut:
        """Fast lookup of the latest stable version using DepGate's resolvers and caching."""
        # Map camelCase args to internal names
        version_range = versionRange
        registry_url = registryUrl
        project_dir = projectDir
        # Validate input
        _validate(
            "lookup",
            {
                "name": name,
                "ecosystem": ecosystem,
                "versionRange": version_range,
                "registryUrl": registry_url,
                "projectDir": project_dir,
            },
        )
        # Enforce sandbox and network policy at the wrapper level
        if args.MCP_PROJECT_DIR and project_dir:
            _sandbox_project_dir(args.MCP_PROJECT_DIR, project_dir)
        _require_online(args, None)
        eco = _eco_from_str(ecosystem) if ecosystem else Ecosystem.NPM
        return _handle_lookup_latest_version(
            name=name,
            eco=eco,
            version_range=version_range,
            registry_url=registry_url,
        )  # type: ignore[return-value]

    @mcp.tool(title="Scan Project", name="Scan_Project", structured_output=True)
    def scan_project(  # pylint: disable=invalid-name,too-many-arguments
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
    ) -> ScanResultOut:
        """Run the standard DepGate pipeline on a project directory."""
        # Map camelCase to internal names
        project_dir = projectDir
        analysis_level = analysisLevel
        _validate(
            "project",
            {
                "projectDir": project_dir,
                "includeDevDependencies": includeDevDependencies,
                "includeTransitive": includeTransitive,
                "respectLockfiles": respectLockfiles,
                "offline": offline,
                "strictProvenance": strictProvenance,
                "paths": paths,
                "analysisLevel": analysis_level,
                "ecosystem": ecosystem,
            },
        )
        if args.MCP_PROJECT_DIR:
            _sandbox_project_dir(args.MCP_PROJECT_DIR, project_dir)
        _require_online(args, offline)
        _reset_state()
        scan_args = _build_cli_args_for_project_scan(project_dir, ecosystem, analysis_level)
        result = _run_scan_pipeline(scan_args)
        try:
            _validate_output_strict(result)
        except Exception as se:
            raise RuntimeError(str(se)) from se
        return result  # type: ignore[return-value]

    @mcp.tool(title="Scan Dependency", name="Scan_Dependency", structured_output=True)
    def scan_dependency(  # pylint: disable=invalid-name,too-many-arguments
        name: str,
        version: str,
        ecosystem: str,
        registryUrl: Optional[str] = None,
        offline: Optional[bool] = None,
        ctx: Any = None,
    ) -> ScanResultOut:
        """Analyze a single dependency (without touching a project tree)."""
        registry_url = registryUrl
        _validate(
            "dependency",
            {
                "name": name,
                "version": version,
                "ecosystem": ecosystem,
                "registryUrl": registry_url,
                "offline": offline,
            },
        )
        _require_online(args, offline)
        eco = _eco_from_str(ecosystem)
        _apply_registry_override(eco, registry_url)
        _reset_state()
        scan_args = _build_args_for_single_dependency(eco, name, version)
        pkglist = build_pkglist(scan_args)
        create_metapackages(scan_args, pkglist)
        apply_version_resolution(scan_args, pkglist)
        check_against(scan_args.package_type, scan_args.LEVEL, metapkg.instances)
        run_analysis(scan_args.LEVEL, scan_args, metapkg.instances)
        result = _gather_results()
        try:
            _validate_output_strict(result)
        except Exception as se:
            raise RuntimeError(str(se)) from se
        return result  # type: ignore[return-value]

    # Run the server in stdio mode (default transport for tests/integration)
    try:
        run_stdio = getattr(mcp, "run_stdio", None)
        if callable(run_stdio):
            run_stdio()
        else:
            mcp.run("stdio")  # type: ignore[arg-type]
    except Exception as exc:  # pragma: no cover - surfaced in stderr
        sys.stderr.write(f"Failed to start MCP stdio server: {exc}\n")
        sys.exit(1)
