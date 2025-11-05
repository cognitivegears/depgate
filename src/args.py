"""Argument parsing for DepGate with action-based CLI (scan as current action)."""

from __future__ import annotations

import argparse
import sys
from typing import List, Optional, Tuple

from constants import Constants


def add_mcp_arguments(parser: argparse.ArgumentParser) -> None:
    """Register arguments for the 'mcp' action (Model Context Protocol server)."""
    # Transport
    parser.add_argument(
        "--host",
        dest="MCP_HOST",
        help="Optional host for non-stdio server (used for streamable HTTP if provided)",
        action="store",
        type=str,
    )
    parser.add_argument(
        "--port",
        dest="MCP_PORT",
        help="Optional port for non-stdio server (used for streamable HTTP if provided)",
        action="store",
        type=int,
    )

    # Project scoping
    parser.add_argument(
        "--project-dir",
        dest="MCP_PROJECT_DIR",
        help="Restrict file access/scan scope to this root directory",
        action="store",
        type=str,
        default=None,
    )

    # Networking / caching
    parser.add_argument(
        "--offline",
        dest="MCP_OFFLINE",
        help="Disable all network calls (tools return offline errors for networked ops)",
        action="store_true",
    )
    parser.add_argument(
        "--no-network",
        dest="MCP_NO_NETWORK",
        help="Hard fail any operation that would require network access",
        action="store_true",
    )
    parser.add_argument(
        "--cache-dir",
        dest="MCP_CACHE_DIR",
        help="Optional cache directory for server-local caches (not required)",
        action="store",
        type=str,
        default=None,
    )
    parser.add_argument(
        "--cache-ttl",
        dest="MCP_CACHE_TTL",
        help="Default cache TTL in seconds for version/HTTP caches (default 600)",
        action="store",
        type=int,
        default=600,
    )

    # Runtime
    parser.add_argument(
        "--log-level",
        dest="LOG_LEVEL",
        help="Set logging level (default INFO)",
        action="store",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
    )
    parser.add_argument(
        "--log-json",
        dest="MCP_LOG_JSON",
        help="Emit structured JSON logs",
        action="store_true",
    )
    parser.add_argument(
        "--max-concurrency",
        dest="MCP_MAX_CONCURRENCY",
        help="Max concurrency for registry/provider requests (advisory)",
        action="store",
        type=int,
        default=None,
    )
    parser.add_argument(
        "--request-timeout",
        dest="MCP_REQUEST_TIMEOUT",
        help="Request timeout in seconds for HTTP operations",
        action="store",
        type=int,
        default=None,
    )


def add_scan_arguments(parser: argparse.ArgumentParser) -> None:
    """Register all existing CLI options under the 'scan' action."""
    # NOTE: This preserves the legacy flags, defaults, and choices exactly.
    parser.add_argument(
        "-t",
        "--type",
        dest="package_type",
        help="Package Manager Type, i.e: npm, PyPI, maven",
        action="store",
        type=str,
        choices=Constants.SUPPORTED_PACKAGES,
        required=True,
    )

    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "-l",
        "--load_list",
        dest="LIST_FROM_FILE",
        help="Load list of dependencies from a file",
        action="append",
        type=str,
        default=[],
    )
    input_group.add_argument(
        "-d",
        "--directory",
        dest="FROM_SRC",
        help="Extract dependencies from local source repository",
        action="append",
        type=str,
    )
    input_group.add_argument(
        "-p",
        "--package",
        dest="SINGLE",
        help="Name a single package.",
        action="append",
        type=str,
    )

    parser.add_argument(
        "-o",
        "--output",
        dest="OUTPUT",
        help="Path to output file (JSON or CSV)",
        action="store",
        type=str,
    )
    parser.add_argument(
        "-f",
        "--format",
        dest="OUTPUT_FORMAT",
        help=(
            "Output format (json or csv). If not specified, inferred from --output extension; "
            "defaults to json."
        ),
        action="store",
        type=str.lower,
        choices=["json", "csv"],
    )

    parser.add_argument(
        "-a",
        "--analysis",
        dest="LEVEL",
        help=(
            "Required analysis level - compare (comp), heuristics (heur), policy (pol), "
            "linked (linked) (default: compare)"
        ),
        action="store",
        default="compare",
        type=str,
        choices=Constants.LEVELS,
    )
    parser.add_argument(
        "--loglevel",
        dest="LOG_LEVEL",
        help="Set the logging level",
        action="store",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="INFO",
    )
    parser.add_argument(
        "--logfile",
        dest="LOG_FILE",
        help="Log output file",
        action="store",
        type=str,
    )
    parser.add_argument(
        "-r",
        "--recursive",
        dest="RECURSIVE",
        help="Recursively scan directories when scanning from source.",
        action="store_true",
    )
    parser.add_argument(
        "--error-on-warnings",
        dest="ERROR_ON_WARNINGS",
        help="Exit with a non-zero status code if warnings are present.",
        action="store_true",
    )
    parser.add_argument(
        "-q",
        "--quiet",
        dest="QUIET",
        help="Do not output to console.",
        action="store_true",
    )

    # Config file (general)
    parser.add_argument(
        "-c",
        "--config",
        dest="CONFIG",
        help="Path to configuration file (YAML, YML, or JSON)",
        action="store",
        type=str,
    )
    parser.add_argument(
        "--set",
        dest="POLICY_SET",
        help="Set policy configuration override (KEY=VALUE format, can be used multiple times)",
        action="append",
        type=str,
        default=[],
    )

    # deps.dev feature flags and tunables (CLI has highest precedence)
    parser.add_argument(
        "--depsdev-disable",
        dest="DEPSDEV_DISABLE",
        help="Disable deps.dev enrichment (feature flag; defaults to enabled)",
        action="store_true",
    )
    parser.add_argument(
        "--depsdev-base-url",
        dest="DEPSDEV_BASE_URL",
        help="Override deps.dev base API URL (default: https://api.deps.dev/v3)",
        action="store",
        type=str,
    )
    parser.add_argument(
        "--depsdev-cache-ttl",
        dest="DEPSDEV_CACHE_TTL",
        help="deps.dev cache TTL in seconds (default: 86400)",
        action="store",
        type=int,
    )
    parser.add_argument(
        "--depsdev-max-concurrency",
        dest="DEPSDEV_MAX_CONCURRENCY",
        help="Maximum concurrent deps.dev requests (default: 4)",
        action="store",
        type=int,
    )
    parser.add_argument(
        "--depsdev-max-response-bytes",
        dest="DEPSDEV_MAX_RESPONSE_BYTES",
        help="Maximum allowed deps.dev response size in bytes (default: 1048576)",
        action="store",
        type=int,
    )
    parser.add_argument(
        "--depsdev-strict-override",
        dest="DEPSDEV_STRICT_OVERRIDE",
        help="Override existing values with deps.dev values (off by default; backfill-only when off)",
        action="store_true",
    )


def build_root_parser() -> Tuple[argparse.ArgumentParser, argparse._SubParsersAction]:
    """Build the root parser and subparsers (actions)."""
    parser = argparse.ArgumentParser(
        prog="depgate",
        description="DepGate - Dependency supply-chain risk and confusion checker",
        add_help=True,
        formatter_class=argparse.RawTextHelpFormatter,
    )
    subparsers = parser.add_subparsers(
        dest="action",
        metavar="<action>",
        title="Actions",
        description=(
            "Available actions:\n"
            "  scan    Analyze dependencies from a package, manifest, or directory\n\n"
            "Use 'depgate <action> --help' for action-specific options.\n"
        ),
        required=False,  # we handle legacy mapping below
    )

    # Register 'scan' action
    scan = subparsers.add_parser(
        "scan",
        help="Analyze dependencies and output results",
        description="Analyze dependencies from package(s), manifests, or source directories.",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    add_scan_arguments(scan)

    # Register 'mcp' action
    mcp = subparsers.add_parser(
        "mcp",
        help="Launch an MCP server exposing DepGate tools",
        description=(
            "Start a Model Context Protocol server with three tools: "
            "Lookup_Latest_Version, Scan_Project, Scan_Dependency.\n\n"
            "Transport: stdio by default. Provide --host/--port to run Streamable HTTP instead."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    add_mcp_arguments(mcp)

    return parser, subparsers


def _is_legacy_invocation(argv: List[str]) -> bool:
    """Return True when args look like the legacy form (no action, options first)."""
    if not argv:
        return False
    # Root help must remain root help
    if argv[0] in ("-h", "--help"):
        return False
    # If the first token starts with '-', treat as legacy (options-first)
    return argv[0].startswith("-")


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse CLI args with action-based syntax, mapping legacy form to 'scan' with warning flag.

    New syntax: depgate <action> [options]
      - Currently supported actions: scan

    Legacy supported for now (deprecation warned once): depgate [options]  -> mapped to: depgate scan [options]
    """
    if argv is None:
        argv = sys.argv[1:]
    parser, _ = build_root_parser()

    legacy = _is_legacy_invocation(argv)
    if legacy:
        argv = ["scan", *argv]

    ns = parser.parse_args(argv)

    # Mark legacy mapping for deprecation warning emission (once)
    if legacy and getattr(ns, "action", None) == "scan":
        setattr(ns, "_deprecated_no_action", True)
    else:
        setattr(ns, "_deprecated_no_action", False)

    return ns
