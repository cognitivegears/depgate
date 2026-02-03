"""Tests for the proxy evaluator."""

import pytest
from src.proxy.evaluator import ProxyEvaluator
from src.proxy.cache import DecisionCache
from src.proxy.request_parser import RegistryType


class TestProxyEvaluator:
    """Tests for ProxyEvaluator."""

    def setup_method(self):
        """Set up test fixtures."""
        # Clear MetaPackage instances before each test
        from metapackage import MetaPackage
        MetaPackage.instances.clear()

    def test_evaluate_no_policy_allows_all(self):
        """Test that no policy config allows all packages."""
        evaluator = ProxyEvaluator()
        decision = evaluator.evaluate("lodash", "4.17.21", RegistryType.NPM)
        assert decision.decision == "allow"
        assert decision.violated_rules == []

    def test_evaluate_with_policy_allow(self):
        """Test evaluation that allows a package with regex include."""
        policy_config = {
            "rules": [{
                "type": "regex",
                "target": "package_name",
                "include": ["lodash"]  # Allow only lodash
            }]
        }
        evaluator = ProxyEvaluator(policy_config=policy_config)
        decision = evaluator.evaluate("lodash", "4.17.21", RegistryType.NPM)
        assert decision.decision == "allow"

    def test_evaluate_with_regex_block(self):
        """Test evaluation that blocks a package by regex."""
        policy_config = {
            "rules": [{
                "type": "regex",
                "target": "package_name",
                "exclude": ["bad-package"]
            }]
        }
        evaluator = ProxyEvaluator(policy_config=policy_config)
        decision = evaluator.evaluate("bad-package", "1.0.0", RegistryType.NPM)
        assert decision.decision == "deny"
        assert any("excluded by pattern" in rule for rule in decision.violated_rules)

    def test_decision_mode_block(self):
        """Test block decision mode."""
        policy_config = {
            "rules": [{
                "type": "regex",
                "target": "package_name",
                "exclude": ["blocked"]
            }]
        }
        evaluator = ProxyEvaluator(policy_config=policy_config, decision_mode="block")
        decision = evaluator.evaluate("blocked-pkg", "1.0.0", RegistryType.NPM)
        assert decision.decision == "deny"

    def test_decision_mode_warn(self):
        """Test warn decision mode allows but records violations."""
        policy_config = {
            "rules": [{
                "type": "regex",
                "target": "package_name",
                "exclude": ["blocked"]
            }]
        }
        evaluator = ProxyEvaluator(policy_config=policy_config, decision_mode="warn")
        decision = evaluator.evaluate("blocked-pkg", "1.0.0", RegistryType.NPM)
        assert decision.decision == "allow"
        assert len(decision.violated_rules) > 0

    def test_decision_mode_audit(self):
        """Test audit decision mode allows but records violations."""
        policy_config = {
            "rules": [{
                "type": "regex",
                "target": "package_name",
                "exclude": ["blocked"]
            }]
        }
        evaluator = ProxyEvaluator(policy_config=policy_config, decision_mode="audit")
        decision = evaluator.evaluate("blocked-pkg", "1.0.0", RegistryType.NPM)
        assert decision.decision == "allow"
        assert len(decision.violated_rules) > 0


class TestProxyEvaluatorCaching:
    """Tests for evaluator caching."""

    def setup_method(self):
        """Set up test fixtures."""
        from metapackage import MetaPackage
        MetaPackage.instances.clear()
        self.cache = DecisionCache(default_ttl=3600)

    def test_cache_hit(self):
        """Test that cached decisions are returned."""
        evaluator = ProxyEvaluator(decision_cache=self.cache)

        # First call - cache miss
        decision1 = evaluator.evaluate("lodash", "4.17.21", RegistryType.NPM)

        # Second call - cache hit
        decision2 = evaluator.evaluate("lodash", "4.17.21", RegistryType.NPM)

        assert decision1.decision == decision2.decision

    def test_cache_invalidation(self):
        """Test cache invalidation."""
        # Need a policy config for caching to occur
        policy_config = {
            "rules": [{
                "type": "regex",
                "target": "package_name",
                "include": ["lodash"]
            }]
        }
        evaluator = ProxyEvaluator(policy_config=policy_config, decision_cache=self.cache)

        # Cache a decision
        evaluator.evaluate("lodash", "4.17.21", RegistryType.NPM)

        # Verify it's cached
        assert self.cache.get("npm", "lodash", "4.17.21") is not None

        # Invalidate
        evaluator.invalidate_cache("npm", "lodash", "4.17.21")

        # Verify it's gone
        assert self.cache.get("npm", "lodash", "4.17.21") is None

    def test_policy_change_clears_cache(self):
        """Test that changing policy clears the cache."""
        evaluator = ProxyEvaluator(decision_cache=self.cache)

        # Cache a decision
        evaluator.evaluate("lodash", "4.17.21", RegistryType.NPM)

        # Change policy
        evaluator.set_policy_config({"rules": []})

        # Cache should be cleared
        assert self.cache.get("npm", "lodash", "4.17.21") is None


class TestProxyEvaluatorRegistries:
    """Tests for different registry types."""

    def setup_method(self):
        """Set up test fixtures."""
        from metapackage import MetaPackage
        MetaPackage.instances.clear()

    def test_evaluate_npm(self):
        """Test NPM package evaluation."""
        evaluator = ProxyEvaluator()
        decision = evaluator.evaluate("lodash", "4.17.21", RegistryType.NPM)
        assert decision.decision == "allow"

    def test_evaluate_pypi(self):
        """Test PyPI package evaluation."""
        evaluator = ProxyEvaluator()
        decision = evaluator.evaluate("requests", "2.31.0", RegistryType.PYPI)
        assert decision.decision == "allow"

    def test_evaluate_maven(self):
        """Test Maven package evaluation."""
        evaluator = ProxyEvaluator()
        decision = evaluator.evaluate(
            "org.apache.commons:commons-lang3", "3.12.0", RegistryType.MAVEN
        )
        assert decision.decision == "allow"

    def test_evaluate_nuget(self):
        """Test NuGet package evaluation."""
        evaluator = ProxyEvaluator()
        decision = evaluator.evaluate("Newtonsoft.Json", "13.0.3", RegistryType.NUGET)
        assert decision.decision == "allow"

    def test_evaluate_without_version(self):
        """Test evaluation without version."""
        evaluator = ProxyEvaluator()
        decision = evaluator.evaluate("lodash", None, RegistryType.NPM)
        assert decision.decision == "allow"
