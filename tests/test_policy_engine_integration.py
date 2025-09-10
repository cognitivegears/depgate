"""Integration tests for policy engine."""

import pytest
from src.analysis.policy import create_policy_engine
from src.analysis.facts import FactBuilder
from metapackage import MetaPackage


class TestPolicyEngineIntegration:
    """Integration tests for the complete policy engine."""

    def test_policy_allow_scenario(self):
        """Test end-to-end policy evaluation that results in allow."""
        # Create a test package
        pkg = MetaPackage("test-package", "npm")
        pkg.score = 0.8
        pkg.repo_stars = 100

        # Create facts
        fact_builder = FactBuilder()
        facts = fact_builder.build_facts(pkg)

        # Create policy engine
        engine = create_policy_engine()

        # Test policy config
        config = {
            "fail_fast": False,
            "metrics": {
                "heuristic_score": {"min": 0.6},
                "stars_count": {"min": 50}
            }
        }

        # Evaluate
        decision = engine.evaluate_policy(facts, config)

        assert decision.decision == "allow"
        assert decision.violated_rules == []

    def test_policy_deny_scenario(self):
        """Test end-to-end policy evaluation that results in deny."""
        # Create a test package
        pkg = MetaPackage("test-package", "npm")
        pkg.score = 0.3  # Below threshold
        pkg.repo_stars = 100

        # Create facts
        fact_builder = FactBuilder()
        facts = fact_builder.build_facts(pkg)

        # Create policy engine
        engine = create_policy_engine()

        # Test policy config
        config = {
            "fail_fast": False,
            "metrics": {
                "heuristic_score": {"min": 0.6},
                "stars_count": {"min": 50}
            }
        }

        # Evaluate
        decision = engine.evaluate_policy(facts, config)

        assert decision.decision == "deny"
        assert len(decision.violated_rules) > 0
        assert "heuristic_score" in decision.violated_rules[0]

    def test_fail_fast_behavior(self):
        """Test fail_fast behavior stops at first violation."""
        # Create a test package
        pkg = MetaPackage("test-package", "npm")
        pkg.score = 0.3  # Will fail first
        pkg.repo_stars = 10  # Will also fail but shouldn't be reached

        # Create facts
        fact_builder = FactBuilder()
        facts = fact_builder.build_facts(pkg)

        # Create policy engine
        engine = create_policy_engine()

        # Test policy config with fail_fast
        config = {
            "fail_fast": True,
            "metrics": {
                "heuristic_score": {"min": 0.6},  # This will fail first
                "stars_count": {"min": 50}  # This would also fail
            }
        }

        # Evaluate
        decision = engine.evaluate_policy(facts, config)

        assert decision.decision == "deny"
        # With fail_fast, should only have one violation
        assert len(decision.violated_rules) == 1
        assert "heuristic_score" in decision.violated_rules[0]

    def test_regex_rule_integration(self):
        """Test regex rule integration."""
        # Create a test package
        pkg = MetaPackage("bad-package", "npm")

        # Create facts
        fact_builder = FactBuilder()
        facts = fact_builder.build_facts(pkg)

        # Create policy engine
        engine = create_policy_engine()

        # Test policy config with regex rule
        config = {
            "fail_fast": False,
            "rules": [{
                "type": "regex",
                "target": "package_name",
                "exclude": ["bad-"]
            }]
        }

        # Evaluate
        decision = engine.evaluate_policy(facts, config)

        assert decision.decision == "deny"
        assert "excluded by pattern" in decision.violated_rules[0]

    def test_license_rule_integration(self):
        """Test license rule integration."""
        # Create a test package
        pkg = MetaPackage("test-package", "npm")

        # Create facts with license info
        fact_builder = FactBuilder()
        facts = fact_builder.build_facts(pkg)
        facts["license"] = {"id": "GPL-3.0-only"}

        # Create policy engine
        engine = create_policy_engine()

        # Test policy config with license rule
        config = {
            "fail_fast": False,
            "rules": [{
                "type": "license",
                "disallowed_licenses": ["GPL-3.0-only"]
            }]
        }

        # Evaluate
        decision = engine.evaluate_policy(facts, config)

        assert decision.decision == "deny"
        assert "GPL-3.0-only is disallowed" in decision.violated_rules[0]

    def test_combined_rules(self):
        """Test combination of different rule types."""
        # Create a test package
        pkg = MetaPackage("good-package", "npm")
        pkg.score = 0.8
        pkg.repo_stars = 100

        # Create facts
        fact_builder = FactBuilder()
        facts = fact_builder.build_facts(pkg)
        facts["license"] = {"id": "MIT"}

        # Create policy engine
        engine = create_policy_engine()

        # Test policy config with multiple rule types
        config = {
            "fail_fast": False,
            "metrics": {
                "heuristic_score": {"min": 0.6},
                "stars_count": {"min": 50}
            },
            "rules": [
                {
                    "type": "regex",
                    "target": "package_name",
                    "include": ["good-"]
                },
                {
                    "type": "license",
                    "disallowed_licenses": ["GPL-3.0-only"]
                }
            ]
        }

        # Evaluate
        decision = engine.evaluate_policy(facts, config)

        assert decision.decision == "allow"
        assert decision.violated_rules == []
