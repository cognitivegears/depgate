import pytest

from src.analysis.policy import create_policy_engine  # type: ignore
from src.analysis.facts import FactBuilder  # type: ignore
from src.metapackage import MetaPackage  # type: ignore


def _make_mp_with_repo(name="pkg", pkg_type="npm"):
    mp = MetaPackage(name, pkg_type)
    # Defaults; tests will override as needed
    mp.repo_url_normalized = "https://github.com/org/repo"
    mp.repo_resolved = True
    mp.repo_exists = True
    mp.repo_host = "github"
    mp.resolved_version = "1.0.0"
    mp.repo_version_match = {
        "matched": True,
        "match_type": "exact",
        "artifact": {"name": "1.0.0"},
        "tag_or_release": "1.0.0",
    }
    return mp


class TestLinkedPolicyRule:
    def test_pass_when_repo_present_and_version_found(self):
        """Allow when source repo is resolved and version exists in SCM."""
        mp = _make_mp_with_repo()
        facts = FactBuilder().build_facts(mp)

        policy = {
            "fail_fast": False,
            "rules": [
                {
                    "type": "linked",
                    "enabled": True,
                    "require_source_repo": True,
                    "require_version_in_source": True,
                }
            ],
        }

        engine = create_policy_engine()
        decision = engine.evaluate_policy(facts, policy)

        assert decision.decision == "allow"
        assert decision.violated_rules == []

    def test_fail_when_repo_missing_and_required(self):
        """Deny when require_source_repo=true and no SCM URL can be resolved."""
        mp = _make_mp_with_repo()
        mp.repo_url_normalized = None
        mp.repo_resolved = None
        mp.repo_exists = None
        facts = FactBuilder().build_facts(mp)

        policy = {
            "rules": [
                {
                    "type": "linked",
                    "enabled": True,
                    "require_source_repo": True,
                }
            ]
        }

        engine = create_policy_engine()
        decision = engine.evaluate_policy(facts, policy)

        assert decision.decision == "deny"
        assert any("no source repository URL resolved" in v for v in decision.violated_rules)

    def test_fail_when_version_not_found_and_required(self):
        """Deny when require_version_in_source=true and version not found; patterns echoed."""
        mp = _make_mp_with_repo()
        mp.resolved_version = "2.0.0"
        mp.repo_version_match = {
            "matched": False,
            "match_type": None,
            "artifact": None,
            "tag_or_release": None,
        }
        facts = FactBuilder().build_facts(mp)

        policy = {
            "rules": [
                {
                    "type": "linked",
                    "enabled": True,
                    "require_version_in_source": True,
                    "version_tag_patterns": ["release-{version}", "v{version}", "{version}"],
                }
            ]
        }

        engine = create_policy_engine()
        decision = engine.evaluate_policy(facts, policy)

        assert decision.decision == "deny"
        # Clear actionable message with repo/version/patterns
        assert any("version not found in SCM" in v for v in decision.violated_rules)
        assert any("release-{version}" in v for v in decision.violated_rules)

    def test_provider_allowlist_blocks_disallowed_host(self):
        """Deny when host is not in allowed_providers."""
        mp = _make_mp_with_repo()
        mp.repo_host = "gitlab"
        facts = FactBuilder().build_facts(mp)

        policy = {
            "rules": [
                {
                    "type": "linked",
                    "enabled": True,
                    "allowed_providers": ["github"],  # disallow gitlab
                }
            ]
        }

        engine = create_policy_engine()
        decision = engine.evaluate_policy(facts, policy)

        assert decision.decision == "deny"
        assert any("SCM provider 'gitlab' is not allowed" in v for v in decision.violated_rules)

    def test_minimal_config_defaults_do_not_enforce(self):
        """Minimal 'linked' rule enabled without require_* flags should allow."""
        mp = _make_mp_with_repo()
        # Remove repo to ensure it's not enforced by default
        mp.repo_url_normalized = None
        mp.repo_resolved = None
        mp.repo_exists = None
        facts = FactBuilder().build_facts(mp)

        policy = {
            "rules": [
                {
                    "type": "linked",
                    "enabled": True,
                }
            ]
        }

        engine = create_policy_engine()
        decision = engine.evaluate_policy(facts, policy)

        assert decision.decision == "allow"
        assert decision.violated_rules == []

    def test_factbuilder_maps_version_found_flag(self):
        """FactBuilder exposes version_found_in_source derived from repo_version_match."""
        mp = _make_mp_with_repo()
        facts = FactBuilder().build_facts(mp)
        assert facts.get("version_found_in_source") is True

        mp.repo_version_match = {
            "matched": False,
            "match_type": None,
            "artifact": None,
            "tag_or_release": None,
        }
        facts2 = FactBuilder().build_facts(mp)
        # When "matched" is False, evaluator should see False (not None)
        assert facts2.get("version_found_in_source") is False


class TestLinkedPolicyNameMatch:
    def test_name_match_exact_pass(self):
        mp = _make_mp_with_repo(name="lodash")
        mp.repo_url_normalized = "https://github.com/acme/lodash"
        facts = FactBuilder().build_facts(mp)

        policy = {"rules": [{"type": "linked", "enabled": True, "name_match": "exact"}]}
        engine = create_policy_engine()
        decision = engine.evaluate_policy(facts, policy)
        assert decision.decision == "allow"

    def test_name_match_exact_fail(self):
        mp = _make_mp_with_repo(name="lodash-es")
        mp.repo_url_normalized = "https://github.com/acme/lodash"
        facts = FactBuilder().build_facts(mp)

        policy = {"rules": [{"type": "linked", "enabled": True, "name_match": "exact"}]}
        engine = create_policy_engine()
        decision = engine.evaluate_policy(facts, policy)
        assert decision.decision == "deny"
        assert any("mode=exact" in v for v in decision.violated_rules)

    def test_name_match_partial_pass(self):
        mp = _make_mp_with_repo(name="lodash-es")
        mp.repo_url_normalized = "https://github.com/acme/lodash"
        facts = FactBuilder().build_facts(mp)

        policy = {"rules": [{"type": "linked", "enabled": True, "name_match": "partial", "name_match_min_len": 3}]}
        engine = create_policy_engine()
        decision = engine.evaluate_policy(facts, policy)
        assert decision.decision == "allow"

    def test_name_match_partial_fail_short_overlap(self):
        mp = _make_mp_with_repo(name="ab")
        mp.repo_url_normalized = "https://github.com/acme/abc"
        facts = FactBuilder().build_facts(mp)

        policy = {"rules": [{"type": "linked", "enabled": True, "name_match": "partial", "name_match_min_len": 3}]}
        engine = create_policy_engine()
        decision = engine.evaluate_policy(facts, policy)
        assert decision.decision == "deny"
        assert any("mode=partial" in v for v in decision.violated_rules)

    def test_name_match_requested_but_no_repo_url_fails(self):
        mp = _make_mp_with_repo(name="mypkg")
        mp.repo_url_normalized = None
        facts = FactBuilder().build_facts(mp)

        policy = {"rules": [{"type": "linked", "enabled": True, "name_match": "exact"}]}
        engine = create_policy_engine()
        decision = engine.evaluate_policy(facts, policy)
        assert decision.decision == "deny"
        assert any("name match requested" in v.lower() for v in decision.violated_rules)
