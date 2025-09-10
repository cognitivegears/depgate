"""Policy engine for evaluating declarative rules against package facts."""

import logging
from typing import Dict, Any, List, Optional
from .policy_rules import rule_evaluator_registry, RuleEvaluator

logger = logging.getLogger(__name__)


class PolicyDecision:
    """Result of policy evaluation."""

    def __init__(self, decision: str, violated_rules: List[str], evaluated_metrics: Dict[str, Any]):
        """Initialize PolicyDecision.

        Args:
            decision: "allow" or "deny"
            violated_rules: List of human-readable violation reasons
            evaluated_metrics: Snapshot of metrics that were evaluated
        """
        self.decision = decision
        self.violated_rules = violated_rules
        self.evaluated_metrics = evaluated_metrics

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation.

        Returns:
            Dict representation of the decision.
        """
        return {
            "decision": self.decision,
            "violated_rules": self.violated_rules,
            "evaluated_metrics": self.evaluated_metrics,
        }


class PolicyEngine:
    """Engine for evaluating policy rules against package facts."""

    def __init__(self):
        """Initialize the PolicyEngine."""
        self._evaluators: Dict[str, RuleEvaluator] = {}

    def register_evaluator(self, rule_type: str, evaluator: RuleEvaluator) -> None:
        """Register a rule evaluator.

        Args:
            rule_type: The rule type.
            evaluator: The rule evaluator instance.
        """
        self._evaluators[rule_type] = evaluator

    def evaluate_policy(self, facts: Dict[str, Any], config: Dict[str, Any]) -> PolicyDecision:
        """Evaluate policy rules against facts.

        Args:
            facts: The facts dictionary.
            config: The policy configuration.

        Returns:
            PolicyDecision with evaluation result.
        """
        fail_fast = config.get("fail_fast", False)
        all_violations = []
        all_evaluated_metrics = {}

        # Evaluate metrics rules
        metrics_config = config.get("metrics", {})
        if metrics_config:
            result = self._evaluate_rule(
                "metrics",
                facts,
                {"metrics": metrics_config, "fail_fast": fail_fast},
            )
            all_violations.extend(result.get("violated_rules", []))
            all_evaluated_metrics.update(result.get("evaluated_metrics", {}))

            if fail_fast and all_violations:
                return PolicyDecision("deny", all_violations, all_evaluated_metrics)

        # Evaluate explicit rules
        rules_config = config.get("rules", [])
        for rule_config in rules_config:
            rule_type = rule_config.get("type")
            if not rule_type:
                continue

            try:
                result = self._evaluate_rule(rule_type, facts, rule_config)
                all_violations.extend(result.get("violated_rules", []))
                all_evaluated_metrics.update(result.get("evaluated_metrics", {}))

                if fail_fast and all_violations:
                    break
            except Exception as e:
                logger.warning(f"Failed to evaluate rule {rule_type}: {str(e)}")
                all_violations.append(f"rule evaluation error: {rule_type}")

        decision = "allow" if not all_violations else "deny"
        return PolicyDecision(decision, all_violations, all_evaluated_metrics)

    def _evaluate_rule(self, rule_type: str, facts: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate a single rule.

        Args:
            rule_type: The type of rule to evaluate.
            facts: The facts dictionary.
            config: The rule configuration.

        Returns:
            Dict with evaluation result.
        """
        if rule_type in self._evaluators:
            evaluator = self._evaluators[rule_type]
        else:
            try:
                evaluator = rule_evaluator_registry.get_evaluator(rule_type)
            except ValueError:
                return {
                    "decision": "deny",
                    "violated_rules": [f"unknown rule type: {rule_type}"],
                    "evaluated_metrics": {},
                }

        return evaluator.evaluate(facts, config)


def create_policy_engine() -> PolicyEngine:
    """Create and configure a PolicyEngine instance.

    Returns:
        Configured PolicyEngine instance.
    """
    engine = PolicyEngine()

    # Register built-in evaluators
    engine.register_evaluator("metrics", rule_evaluator_registry.get_evaluator("metrics"))
    engine.register_evaluator("regex", rule_evaluator_registry.get_evaluator("regex"))
    engine.register_evaluator("license", rule_evaluator_registry.get_evaluator("license"))

    return engine
