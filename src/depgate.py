"""DepGate CLI entrypoint (orchestrator).

This file coordinates the CLI flow and delegates real work to modular helpers.
"""

# pylint: disable=too-many-branches, too-many-statements
from __future__ import annotations

import logging
import os
import sys

from args import parse_args
from constants import ExitCodes
from common.logging_utils import configure_logging, is_debug_enabled, extra_context
from metapackage import MetaPackage as metapkg

from cli_config import apply_depsdev_overrides
from cli_io import print_banner, export_csv, export_json
from cli_build import (
    build_pkglist,
    create_metapackages,
    apply_version_resolution,
    determine_exit_code,
)
from cli_classify import apply_classification
from cli_registry import check_against
from analysis.analysis_runner import run_analysis


def _run_scan(args) -> None:
    """Execute the legacy scan workflow (now the 'scan' action handler)."""
    logger = logging.getLogger(__name__)

    # Banner
    print_banner()

    # Build package list (from file, source dir, or single token)
    pkglist = build_pkglist(args)
    if is_debug_enabled(logger):
        logger.debug(
            "Built package list",
            extra=extra_context(
                event="decision",
                component="cli",
                action="build_pkglist",
                outcome="empty" if not pkglist else "non_empty",
                count=len(pkglist) if isinstance(pkglist, list) else 0,
            ),
        )
    if not pkglist or not isinstance(pkglist, list):
        logging.warning("No packages found in the input list.")
        if is_debug_enabled(logger):
            logger.debug(
                "CLI finished (no packages)",
                extra=extra_context(
                    event="function_exit", component="cli", action="main", outcome="no_packages"
                ),
            )
            logger.debug(
                "CLI finished",
                extra=extra_context(
                    event="function_exit", component="cli", action="main", outcome="success"
                ),
            )
        sys.exit(ExitCodes.SUCCESS.value)

    logging.info("Package list imported: %s", str(pkglist))

    # Instantiate MetaPackage objects
    create_metapackages(args, pkglist)

    # Auto-classify dependency relation/scope/requirement for source scans (best-effort)
    try:
        apply_classification(args, metapkg.instances)
    except Exception:  # pylint: disable=broad-exception-caught
        # best-effort; never fail CLI on classification
        pass

    # Resolve requested specs to versions (best-effort)
    apply_version_resolution(args, pkglist)

    # Query registries and populate data
    if is_debug_enabled(logger):
        logger.debug(
            "Checking against registry",
            extra=extra_context(
                event="function_entry",
                component="cli",
                action="check_against",
                target=args.package_type,
                outcome="starting",
            ),
        )
    check_against(args.package_type, args.LEVEL, metapkg.instances)
    if is_debug_enabled(logger):
        logger.debug(
            "Finished checking against registry",
            extra=extra_context(
                event="function_exit",
                component="cli",
                action="check_against",
                target=args.package_type,
                outcome="completed",
            ),
        )

    # Analyze
    run_analysis(args.LEVEL, args, metapkg.instances)

    # Output
    if getattr(args, "OUTPUT", None):
        fmt = getattr(args, "OUTPUT_FORMAT", None)
        if not fmt:
            lower = args.OUTPUT.lower()
            if lower.endswith(".json"):
                fmt = "json"
            elif lower.endswith(".csv"):
                fmt = "csv"
        if fmt is None:
            fmt = "json"
        if fmt == "csv":
            export_csv(metapkg.instances, args.OUTPUT)
        else:
            export_json(metapkg.instances, args.OUTPUT)

    # Exit according to risk/warning flags
    determine_exit_code(args)
def main() -> None:
    """Main CLI entrypoint that orchestrates the DepGate workflow."""
    logger = logging.getLogger(__name__)

    # Parse CLI arguments (supports action-based syntax; legacy mapped to 'scan')
    args = parse_args()

    # Honor CLI --loglevel by passing it to centralized logger via env
    if getattr(args, "LOG_LEVEL", None):
        os.environ["DEPGATE_LOG_LEVEL"] = str(args.LOG_LEVEL).upper()

    # Configure logging, then ensure runtime CLI flag wins regardless of environment defaults
    configure_logging()
    try:
        level_name = str(getattr(args, "LOG_LEVEL", "INFO")).upper()
        level_value = getattr(logging, level_name, logging.INFO)
        logging.getLogger().setLevel(level_value)
    except Exception:  # pylint: disable=broad-exception-caught
        # Defensive: never break CLI on logging setup
        pass

    # Apply CLI overrides for deps.dev feature and tunables (CLI has highest precedence)
    apply_depsdev_overrides(args)

    if is_debug_enabled(logger):
        logger.debug(
            "CLI start",
            extra=extra_context(event="function_entry", component="cli", action="main"),
        )

    # Emit a single deprecation warning for legacy no-action invocation
    if getattr(args, "_deprecated_no_action", False):
        try:
            sys.stderr.write(
                (
                    "DEPRECATION: The legacy invocation without an action is deprecated "
                    "and will be removed in a future release. Use: depgate scan [options].\n"
                )
            )
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    # Dispatch by action
    action = getattr(args, "action", None)
    if not action:
        # Top-level usage/help summary
        sys.stderr.write(
            "Usage: depgate <action> [options]\n\n"
            "Actions:\n"
            "  scan    Analyze dependencies from a package, manifest, or directory\n\n"
            "Use 'depgate <action> --help' for action-specific options.\n"
        )
        sys.exit(ExitCodes.SUCCESS.value)

    if action == "scan":
        _run_scan(args)
        return

    if action == "mcp":
        # Lazy import to avoid importing MCP SDK for other commands
        from cli_mcp import run_mcp_server  # type: ignore
        run_mcp_server(args)
        return

    # Unknown action safeguard (argparse typically catches this already)
    sys.stderr.write(f"Unknown action '{action}'. Available actions: scan, mcp\n")
    sys.exit(2)


if __name__ == "__main__":
    main()
