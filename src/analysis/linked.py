"""Linked analysis: mirrors compare baseline and adds repository linkage verification.

This module reuses existing repository enrichment signals populated during
registry checks and extends the compare baseline with linkage checks:
- repository URL resolved and exists
- version tag or release matches the package version (including v-prefix)
The analysis logs per-package results and a final summary, and sets fields
on each MetaPackage instance for JSON export when -a linked is used.
"""
from __future__ import annotations

import logging
from typing import Sequence

from constants import Constants
from analysis import heuristics as _heur  # pylint: disable=import-outside-toplevel

STG = f"{Constants.ANALYSIS} "


def run_linked(args, instances: Sequence[object]) -> None:  # pylint: disable=unused-argument
    """Run linked analysis.

    Mirrors compare baseline (run_min_analysis) and then performs linkage checks.
    Populates additional fields used by export_json when in linked mode.
    """
    logger = logging.getLogger(__name__)

    # Mark mode for downstream exporters
    for mp in instances:
        try:
            setattr(mp, "_linked_mode", True)
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    logging.info("%sLinked analysis started.", STG)

    # Mirror compare baseline (existence checks and summary)
    _heur.run_min_analysis(instances)

    # Per-package linkage verification
    linked_pass = 0
    total = len(instances)
    for x in instances:
        # Collect repo signals
        repo_url = getattr(x, "repo_url_normalized", None)
        repo_resolved = bool(getattr(x, "repo_resolved", False))
        repo_exists = (getattr(x, "repo_exists", None) is True)
        vm = getattr(x, "repo_version_match", None)
        release_match = bool(getattr(x, "_version_match_release_matched", False))
        tag_match = bool(getattr(x, "_version_match_tag_matched", False))

        # Log repository linkage details
        try:
            logging.info("%s.... repository URL: %s.", STG, repo_url if repo_url else "not found")
            logging.info("%s.... repository resolved: %s, exists: %s.", STG, str(repo_resolved), str(repo_exists))
            if vm is None:
                logging.info("%s.... repository version match: unavailable.", STG)
            else:
                _matched = bool(vm.get("matched", False))
                _mtype = vm.get("match_type", None)
                _artifact = vm.get("tag_or_release", None)
                _via = "release" if release_match else ("tag" if tag_match else "unknown")
                logging.info(
                    "%s.... repository version match: %s (type: %s, via: %s, artifact: %s).",
                    STG,
                    "yes" if _matched else "no",
                    str(_mtype),
                    _via,
                    str(_artifact),
                )
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        # Determine linkage pass/fail
        baseline_ok = (getattr(x, "exists", None) is True)
        match_ok = False
        try:
            match_ok = bool(vm and vm.get("matched", False))
        except Exception:  # pylint: disable=broad-exception-caught
            match_ok = False
        repo_ok = (repo_url is not None) and repo_resolved and repo_exists
        is_linked = bool(baseline_ok and repo_ok and match_ok)

        # Persist fields for JSON export
        try:
            setattr(x, "_linked_tag_match", tag_match)
            setattr(x, "_linked_release_match", release_match)
            setattr(x, "linked", is_linked)
        except Exception:  # pylint: disable=broad-exception-caught
            pass

        if is_linked:
            linked_pass += 1
            logging.info("%s.... linked result: PASS.", STG)
        else:
            logging.warning("%s.... linked result: FAIL.", STG)

    pct = (linked_pass / total * 100.0) if total > 0 else 0.0
    logging.info("%sLinked summary: %d out of %d packages linked (%.2f%% of total).", STG, linked_pass, total, pct)
