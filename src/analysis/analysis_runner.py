"""Top-level analysis runner for the DepGate CLI.

This thin wrapper keeps depgate.py small by routing to heuristics or policy flows.
"""

from __future__ import annotations

import logging
from typing import Sequence

from constants import Constants


def run_analysis(level: str, args, instances: Sequence[object]) -> None:
    """Run the selected analysis for collected packages.

    Args:
        level: CLI-selected analysis level (e.g., compare/heur/policy)
        args: Parsed CLI args (used by policy runner)
        instances: Iterable of MetaPackage-like objects
    """
    # Import lazily to avoid heavy deps during --help
    from analysis import heuristics as _heur  # pylint: disable=import-outside-toplevel

    if level in (Constants.LEVELS[0], Constants.LEVELS[1]):
        _heur.run_min_analysis(instances)
        return

    if level in (Constants.LEVELS[2], Constants.LEVELS[3]):
        _heur.run_heuristics(instances)
        return

    if level == "linked":
        try:
            from analysis.linked import run_linked  # pylint: disable=import-outside-toplevel
            run_linked(args, instances)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logging.getLogger(__name__).error("Linked analysis error: %s", exc)
        return

    if level in ("policy", "pol"):
        try:
            from analysis.policy_runner import (  # pylint: disable=import-outside-toplevel
                run_policy_analysis,
            )
            run_policy_analysis(args, instances)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # Never fail CLI due to policy engine errors
            logging.getLogger(__name__).error("Policy analysis error: %s", exc)
        return

    # Unknown level is ignored to preserve backward behavior
    logging.getLogger(__name__).warning("Unknown analysis level '%s' – skipping.", level)
