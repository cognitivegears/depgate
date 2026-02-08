"""Tests for built-in policy presets."""

from analysis.policy import create_policy_engine
from analysis.policy_runner import build_policy_preset


def test_default_policy_preset():
    config = build_policy_preset("default")
    assert config.get("metrics", {}).get("heuristic_score", {}).get("min") == 0.6
    assert config.get("metrics", {}).get("stars_count", {}).get("min") == 5


def test_supply_chain_policy_preset_allow_unknown():
    config = build_policy_preset("supply-chain", min_release_age_days=7)
    assert "rules" in config and isinstance(config["rules"], list)
    rule = config["rules"][0]
    assert rule["type"] == "metrics"
    assert rule["allow_unknown"] is True
    assert rule["metrics"]["release_age_days"]["min"] == 7
    assert rule["metrics"]["supply_chain_trust_score_delta"]["min"] == 0
    assert rule["metrics"]["provenance_regressed"]["eq"] is False
    assert rule["metrics"]["registry_signature_regressed"]["eq"] is False


def test_supply_chain_policy_preset_strict():
    config = build_policy_preset("supply-chain-strict", min_release_age_days=5)
    rule = config["rules"][0]
    assert rule["allow_unknown"] is False
    assert rule["metrics"]["release_age_days"]["min"] == 5


def test_supply_chain_policy_preset_denies_on_regressions_and_age():
    engine = create_policy_engine()
    config = build_policy_preset("supply-chain", min_release_age_days=3)

    facts = {
        "release_age_days": 1,
        "supply_chain_trust_score_delta": -0.1,
        "provenance_regressed": True,
        "registry_signature_regressed": True,
    }
    decision = engine.evaluate_policy(facts, config)

    assert decision.decision == "deny"
    assert any("release_age_days" in msg for msg in decision.violated_rules)
    assert any("supply_chain_trust_score_delta" in msg for msg in decision.violated_rules)
    assert any("provenance_regressed" in msg for msg in decision.violated_rules)
    assert any("registry_signature_regressed" in msg for msg in decision.violated_rules)
