"""Policy analysis runner extracted from depgate.py.

Evaluates policy decisions for collected packages:
- Builds facts per package
- Optionally runs heuristics and license discovery to fill missing facts
- Loads policy configuration (CLI overrides & YAML config precedence)
- Evaluates policy and annotates packages with results
"""

# pylint: disable=too-many-locals, too-many-branches, too-many-statements, import-outside-toplevel
from __future__ import annotations

import json
import logging
from typing import Sequence
from constants import Constants


def run_policy_analysis(args, instances: Sequence[object]) -> None:
    """Run policy analysis for collected packages.

    Args:
        args: Parsed CLI args (provides CONFIG and POLICY_SET)
        instances: Iterable of MetaPackage-like objects (with pkg_name and repo_url_normalized)
    """
    # Import policy modules lazily to keep CLI help fast
    from analysis.facts import FactBuilder  # pylint: disable=import-outside-toplevel
    from analysis.policy import create_policy_engine  # pylint: disable=import-outside-toplevel
    from repository.license_discovery import (  # pylint: disable=import-outside-toplevel
        license_discovery,
    )
    from analysis import heuristics as _heur  # pylint: disable=import-outside-toplevel

    logger = logging.getLogger(__name__)
    STG = f"{Constants.ANALYSIS} "

    # Step 1: Build facts for all packages
    fact_builder = FactBuilder()
    all_facts: dict[str, dict] = {}
    for pkg in instances:
        try:
            facts = fact_builder.build_facts(pkg)
        except Exception:  # pylint: disable=broad-exception-caught
            facts = {}
        all_facts[getattr(pkg, "pkg_name", "<unknown>")] = facts

    # Step 2: Check if heuristics are needed (simplified gate)
    heuristic_metrics_needed = ["heuristic_score", "is_license_available"]
    for pkg in instances:
        pname = getattr(pkg, "pkg_name", "<unknown>")
        facts = all_facts.get(pname, {})
        needs_heuristics = any(facts.get(key) in (None, "") for key in heuristic_metrics_needed)
        if needs_heuristics:
            try:
                _heur.run_heuristics([pkg])
                facts["heuristic_score"] = getattr(pkg, "score", None)
                facts["is_license_available"] = getattr(pkg, "is_license_available", None)
            except Exception:  # pylint: disable=broad-exception-caught
                # Best-effort
                pass

    # Step 3: License discovery when we have a repo_url but no license facts
    for pkg in instances:
        pname = getattr(pkg, "pkg_name", "<unknown>")
        facts = all_facts.get(pname, {})
        try:
            has_id = bool((facts.get("license") or {}).get("id"))
            repo_url = getattr(pkg, "repo_url_normalized", None)
            if not has_id and repo_url:
                try:
                    license_info = license_discovery.discover_license(repo_url, "default")
                    facts["license"] = license_info
                except Exception:  # pylint: disable=broad-exception-caught
                    # Keep as-is on failure
                    pass
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    # Step 4: Policy engine and config loading
    policy_engine = create_policy_engine()

    def _load_policy_from_user_config(cli_args):
        """Return policy dict from user config if available; otherwise None."""
        cfg = {}
        # Explicit --config path (supports YAML or JSON)
        path = getattr(cli_args, "CONFIG", None)
        if isinstance(path, str) and path.strip():
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    lower = path.lower()
                    if lower.endswith(".json"):
                        try:
                            cfg = json.load(fh) or {}
                        except Exception:  # pylint: disable=broad-exception-caught
                            cfg = {}
                    else:
                        try:
                            import yaml as _yaml  # type: ignore
                        except Exception:  # pylint: disable=broad-exception-caught
                            _yaml = None
                        if _yaml is not None:
                            try:
                                cfg = _yaml.safe_load(fh) or {}
                            except Exception:  # pylint: disable=broad-exception-caught
                                cfg = {}
                        else:
                            cfg = {}
            except Exception:  # pylint: disable=broad-exception-caught
                cfg = {}
        # Fallback: default YAML locations handled by constants
        if not cfg:
            try:
                from constants import _load_yaml_config as _defaults_loader  # type: ignore
                cfg = _defaults_loader() or {}
            except Exception:  # pylint: disable=broad-exception-caught
                cfg = {}
        if isinstance(cfg, dict):
            pol = cfg.get("policy")
            if isinstance(pol, dict):
                return pol
        return None

    def _coerce_value(text):
        """Best-effort convert string to JSON/number/bool, else raw string."""
        s = str(text).strip()
        try:
            return json.loads(s)
        except Exception:  # pylint: disable=broad-exception-caught
            sl = s.lower()
            if sl == "true":
                return True
            if sl == "false":
                return False
            try:
                if s.isdigit() or (s.startswith("-") and s[1:].isdigit()):
                    return int(s)
                return float(s)
            except Exception:  # pylint: disable=broad-exception-caught
                return s

    def _apply_dot_path(dct, dot_path, value):
        parts = [p for p in dot_path.split(".") if p]
        cur = dct
        for key in parts[:-1]:
            if key not in cur or not isinstance(cur.get(key), dict):
                cur[key] = {}
            cur = cur[key]
        cur[parts[-1]] = value

    def _collect_policy_overrides(pairs):
        overrides = {}
        if not pairs:
            return overrides
        for item in pairs:
            if not isinstance(item, str) or "=" not in item:
                continue
            key, val = item.split("=", 1)
            key = key.strip()
            if key.startswith("policy."):
                key = key[len("policy.") :]
            _apply_dot_path(overrides, key, _coerce_value(val.strip()))
        return overrides

    user_policy = _load_policy_from_user_config(args)
    overrides_present = bool(getattr(args, "POLICY_SET", None))

    if user_policy is not None:
        policy_config = dict(user_policy)  # shallow copy from user config
    elif overrides_present:
        # If overrides are provided but no user policy config exists, start from empty
        policy_config = {}
    else:
        # Built-in fallback defaults
        policy_config = {
            "fail_fast": False,
            "metrics": {
                "stars_count": {"min": 5},
                "heuristic_score": {"min": 0.6},
            },
        }

    if overrides_present:
        ov = _collect_policy_overrides(getattr(args, "POLICY_SET", []))

        def _deep_merge(dest, src):
            for k, v in src.items():
                if isinstance(v, dict) and isinstance(dest.get(k), dict):
                    _deep_merge(dest[k], v)
                else:
                    dest[k] = v

        _deep_merge(policy_config, ov)

    # Evaluate each package
    for pkg in instances:
        pname = getattr(pkg, "pkg_name", "<unknown>")
        facts = all_facts.get(pname, {})
        try:
            decision = policy_engine.evaluate_policy(facts, policy_config)
            # Store decision on package for output
            pkg.policy_decision = decision.decision
            pkg.policy_violated_rules = decision.violated_rules
            pkg.policy_evaluated_metrics = decision.evaluated_metrics
            # Debug-level details
            try:
                logger.debug(
                    "[policy] evaluated package=%s decision=%s violations=%d details=%s",
                    pname, decision.decision, len(decision.violated_rules or []),
                    "; ".join(decision.violated_rules or [])
                )
            except Exception:
                pass
            # Single ANALYSIS outcome log (INFO)
            try:
                logger.info(
                    "%sPolicy outcome: %s for %s (%d violations).",
                    STG, decision.decision.upper(), pname, len(decision.violated_rules or [])
                )
            except Exception:
                pass
            # Existing result logs
            if decision.decision == "deny":
                logger.warning("Policy DENY for %s: %s", pname, ", ".join(decision.violated_rules))
            else:
                # Demote non-ANALYSIS outcome to debug to avoid duplicate INFO logs
                logger.debug("Policy ALLOW for %s", pname)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.error("Policy evaluation error for %s: %s", pname, exc)
