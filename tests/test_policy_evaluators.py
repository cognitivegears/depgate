"""Tests for policy rule evaluators."""

import pytest
from src.analysis.policy_rules import (
    MetricComparatorEvaluator, RegexRuleEvaluator, LicenseRuleEvaluator
)


class TestMetricComparatorEvaluator:
    """Test MetricComparatorEvaluator."""

    def test_metric_comparison_allow(self):
        """Test metric comparison that allows."""
        evaluator = MetricComparatorEvaluator()
        facts = {
            "stars_count": 10,
            "heuristic_score": 0.8
        }
        config = {
            "metrics": {
                "stars_count": {"min": 5},
                "heuristic_score": {"min": 0.6}
            }
        }
        result = evaluator.evaluate(facts, config)
        assert result["decision"] == "allow"
        assert result["violated_rules"] == []

    def test_metric_comparison_deny(self):
        """Test metric comparison that denies."""
        evaluator = MetricComparatorEvaluator()
        facts = {
            "stars_count": 3,
            "heuristic_score": 0.8
        }
        config = {
            "metrics": {
                "stars_count": {"min": 5},
                "heuristic_score": {"min": 0.6}
            }
        }
        result = evaluator.evaluate(facts, config)
        assert result["decision"] == "deny"
        assert len(result["violated_rules"]) == 1

    def test_missing_fact_with_allow_unknown(self):
        """Test missing fact with allow_unknown=true."""
        evaluator = MetricComparatorEvaluator()
        facts = {
            "stars_count": 10
            # heuristic_score is missing
        }
        config = {
            "allow_unknown": True,
            "metrics": {
                "stars_count": {"min": 5},
                "heuristic_score": {"min": 0.6}
            }
        }
        result = evaluator.evaluate(facts, config)
        assert result["decision"] == "allow"

    def test_missing_fact_without_allow_unknown(self):
        """Test missing fact with allow_unknown=false."""
        evaluator = MetricComparatorEvaluator()
        facts = {
            "stars_count": 10
            # heuristic_score is missing
        }
        config = {
            "allow_unknown": False,
            "metrics": {
                "stars_count": {"min": 5},
                "heuristic_score": {"min": 0.6}
            }
        }
        result = evaluator.evaluate(facts, config)
        assert result["decision"] == "deny"
        assert "missing fact: heuristic_score" in result["violated_rules"][0]


class TestRegexRuleEvaluator:
    """Test RegexRuleEvaluator."""

    def test_include_only_allow(self):
        """Test include-only pattern that allows."""
        evaluator = RegexRuleEvaluator()
        facts = {"package_name": "my-org-package"}
        config = {
            "target": "package_name",
            "include": ["^my-org-"]
        }
        result = evaluator.evaluate(facts, config)
        assert result["decision"] == "allow"

    def test_include_only_deny(self):
        """Test include-only pattern that denies."""
        evaluator = RegexRuleEvaluator()
        facts = {"package_name": "other-package"}
        config = {
            "target": "package_name",
            "include": ["^my-org-"]
        }
        result = evaluator.evaluate(facts, config)
        assert result["decision"] == "deny"

    def test_exclude_precedence(self):
        """Test that exclude takes precedence over include."""
        evaluator = RegexRuleEvaluator()
        facts = {"package_name": "my-org-beta"}
        config = {
            "target": "package_name",
            "include": ["^my-org-"],
            "exclude": ["-beta$"]
        }
        result = evaluator.evaluate(facts, config)
        assert result["decision"] == "deny"
        assert "excluded by pattern" in result["violated_rules"][0]

    def test_case_sensitive_default(self):
        """Test case sensitive matching (default)."""
        evaluator = RegexRuleEvaluator()
        facts = {"package_name": "My-Org-Package"}
        config = {
            "target": "package_name",
            "include": ["^my-org-"]
        }
        result = evaluator.evaluate(facts, config)
        assert result["decision"] == "deny"

    def test_case_insensitive(self):
        """Test case insensitive matching."""
        evaluator = RegexRuleEvaluator()
        facts = {"package_name": "My-Org-Package"}
        config = {
            "target": "package_name",
            "include": ["^my-org-"],
            "case_sensitive": False
        }
        result = evaluator.evaluate(facts, config)
        assert result["decision"] == "allow"

    def test_full_match_true(self):
        """Test full match mode."""
        evaluator = RegexRuleEvaluator()
        facts = {"package_name": "test-package-extra"}
        config = {
            "target": "package_name",
            "include": ["^test-package$"],
            "full_match": True
        }
        result = evaluator.evaluate(facts, config)
        assert result["decision"] == "deny"

    def test_missing_target(self):
        """Test missing target value."""
        evaluator = RegexRuleEvaluator()
        facts = {"other_field": "value"}
        config = {
            "target": "package_name",
            "include": ["^test-"]
        }
        result = evaluator.evaluate(facts, config)
        assert result["decision"] == "deny"
        assert "missing target value" in result["violated_rules"][0]


class TestLicenseRuleEvaluator:
    """Test LicenseRuleEvaluator."""

    def test_allowed_license(self):
        """Test allowed license."""
        evaluator = LicenseRuleEvaluator()
        facts = {"license": {"id": "MIT"}}
        config = {
            "disallowed_licenses": ["GPL-3.0-only"]
        }
        result = evaluator.evaluate(facts, config)
        assert result["decision"] == "allow"

    def test_disallowed_license(self):
        """Test disallowed license."""
        evaluator = LicenseRuleEvaluator()
        facts = {"license": {"id": "GPL-3.0-only"}}
        config = {
            "disallowed_licenses": ["GPL-3.0-only"]
        }
        result = evaluator.evaluate(facts, config)
        assert result["decision"] == "deny"
        assert "GPL-3.0-only is disallowed" in result["violated_rules"][0]

    def test_unknown_license_with_allow_unknown(self):
        """Test unknown license with allow_unknown=true."""
        evaluator = LicenseRuleEvaluator()
        facts = {"license": {"id": None}}
        config = {
            "disallowed_licenses": ["GPL-3.0-only"],
            "allow_unknown": True
        }
        result = evaluator.evaluate(facts, config)
        assert result["decision"] == "allow"

    def test_unknown_license_without_allow_unknown(self):
        """Test unknown license with allow_unknown=false."""
        evaluator = LicenseRuleEvaluator()
        facts = {"license": {"id": None}}
        config = {
            "disallowed_licenses": ["GPL-3.0-only"],
            "allow_unknown": False
        }
        result = evaluator.evaluate(facts, config)
        assert result["decision"] == "deny"
        assert "license unknown" in result["violated_rules"][0]

    def test_missing_license_field(self):
        """Test missing license field."""
        evaluator = LicenseRuleEvaluator()
        facts = {}
        config = {
            "disallowed_licenses": ["GPL-3.0-only"],
            "allow_unknown": False
        }
        result = evaluator.evaluate(facts, config)
        assert result["decision"] == "deny"
        assert "license unknown" in result["violated_rules"][0]
