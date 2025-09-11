"""Validation tests for depgate.example.yml policy section and engine compatibility."""

import os
import importlib
import yaml

from src.analysis.policy import create_policy_engine


def _example_yaml_path() -> str:
    return os.path.join(os.getcwd(), "docs", "depgate.example.yml")


def test_example_yaml_loads_via_constants(monkeypatch):
    """Ensure the example YAML loads via constants loader and unknown keys are ignored."""
    path = _example_yaml_path()
    assert os.path.isfile(path)

    # Point loader to example; reload constants to apply (values match defaults, so safe)
    monkeypatch.setenv("DEPGATE_CONFIG", path)
    import src.constants as constants  # noqa: PLC0415
    importlib.reload(constants)

    # Known keys apply (these values match the example and defaults)
    assert isinstance(constants.Constants.REQUEST_TIMEOUT, int)
    assert constants.Constants.REQUEST_TIMEOUT == 30

    # Unknown top-level 'policy' key is intentionally ignored by loader
    assert not hasattr(constants, "POLICY")


def test_example_policy_schema_compatible_with_engine_allows():
    """Parse policy from example YAML and verify engine evaluates an allow decision."""
    path = _example_yaml_path()
    with open(path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    policy = cfg.get("policy", {})

    engine = create_policy_engine()

    # Facts chosen to satisfy metrics and regex include; license allowed
    facts = {
        "package_name": "@acme/pkg",
        "registry": "npm",
        "stars_count": 999,
        "contributors_count": 5,
        "version_count": 2,
        "heuristic_score": 0.9,
        "license": {"id": "MIT"},
    }

    decision = engine.evaluate_policy(facts, policy)
    assert decision.decision == "allow"
    assert decision.violated_rules == []


def test_example_policy_schema_compatible_with_engine_denies_disallowed_license():
    """Parse policy from example YAML and verify engine denies a disallowed license."""
    path = _example_yaml_path()
    with open(path, "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    policy = cfg.get("policy", {})

    engine = create_policy_engine()

    # Facts satisfy metrics and regex include, but license is disallowed
    facts = {
        "package_name": "@acme/pkg",
        "registry": "npm",
        "stars_count": 999,
        "contributors_count": 5,
        "version_count": 2,
        "heuristic_score": 0.9,
        "license": {"id": "GPL-3.0-only"},
    }

    decision = engine.evaluate_policy(facts, policy)
    assert decision.decision == "deny"
    assert any("GPL-3.0-only is disallowed" in v for v in decision.violated_rules)


def test_rule_metrics_allow_unknown_allows_missing():
    """Rule-level metrics can set allow_unknown=True and pass missing facts."""
    engine = create_policy_engine()
    policy = {
        "fail_fast": False,
        "rules": [
            {
                "type": "metrics",
                "allow_unknown": True,
                "metrics": {
                    "nonexistent.fact": {"min": 1}
                },
            }
        ],
    }
    facts = {}
    decision = engine.evaluate_policy(facts, policy)
    assert decision.decision == "allow"
    assert decision.violated_rules == []


def test_metrics_unknown_comparator_records_violation():
    """Top-level metrics with unknown comparator produces a violation."""
    engine = create_policy_engine()
    policy = {
        "metrics": {
            "stars_count": {"unknown_op": 1}
        }
    }
    facts = {"stars_count": 5}
    decision = engine.evaluate_policy(facts, policy)
    assert decision.decision == "deny"
    assert any("unknown comparator" in v for v in decision.violated_rules)


def test_top_level_license_check_is_ignored_by_engine():
    """Demonstrate that 'license_check' at top-level is ignored by the engine (not implemented)."""
    engine = create_policy_engine()
    policy = {
        "license_check": {
            "enabled": True,
            "disallowed_licenses": ["GPL-3.0-only"]
        }
    }
    facts = {"license": {"id": "GPL-3.0-only"}}
    decision = engine.evaluate_policy(facts, policy)
    # Because license_check is ignored, decision remains 'allow'
    assert decision.decision == "allow"
