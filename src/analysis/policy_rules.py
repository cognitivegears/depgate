"""Policy rule evaluators for different types of constraints."""

import re
import logging
from typing import Dict, Any, List, Optional, Union
from .policy_comparators import comparator_registry, Comparator

logger = logging.getLogger(__name__)


class RuleEvaluator:
    """Base class for rule evaluators."""

    def evaluate(self, facts: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate a rule against facts.

        Args:
            facts: The facts dictionary.
            config: The rule configuration.

        Returns:
            Dict with evaluation result.
        """
        raise NotImplementedError


class MetricComparatorEvaluator(RuleEvaluator):
    """Evaluator for metric-based comparison rules."""

    def evaluate(self, facts: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate metric comparison rules.

        Args:
            facts: The facts dictionary.
            config: The rule configuration containing metrics map.

        Returns:
            Dict with evaluation result.
        """
        violations = []
        evaluated_metrics = {}

        metrics_config = config.get("metrics", {})
        allow_unknown = config.get("allow_unknown", False)
        fail_fast = config.get("fail_fast", False)

        for metric_path, constraints in metrics_config.items():
            if not isinstance(constraints, dict):
                continue

            actual_value = self._get_nested_value(facts, metric_path)
            evaluated_metrics[metric_path] = actual_value

            if actual_value is None:
                if not allow_unknown:
                    violations.append(f"missing fact: {metric_path}")
                    if fail_fast:
                        break
                continue

            for comp_name, expected_value in constraints.items():
                try:
                    comparator = comparator_registry.get_comparator(comp_name)
                    if not comparator.compare(actual_value, expected_value):
                        violations.append(
                            f"{metric_path} {comp_name} {expected_value} failed "
                            f"(actual: {actual_value})"
                        )
                        if fail_fast:
                            break
                except ValueError:
                    violations.append(f"unknown comparator: {comp_name}")
                    if fail_fast:
                        break
                except Exception as e:
                    violations.append(f"comparison error for {metric_path}: {str(e)}")
                    if fail_fast:
                        break
            if fail_fast and violations:
                break

        decision = "allow" if not violations else "deny"

        return {
            "decision": decision,
            "violated_rules": violations,
            "evaluated_metrics": evaluated_metrics,
        }

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """Get nested value from dict using dot notation.

        Args:
            data: The data dictionary.
            path: Dot-separated path (e.g., "license.id").

        Returns:
            The value at the path, or None if not found.
        """
        keys = path.split(".")
        current = data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None

        return current


class RegexRuleEvaluator(RuleEvaluator):
    """Evaluator for regex-based rules."""

    def evaluate(self, facts: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate regex rules.

        Args:
            facts: The facts dictionary.
            config: The rule configuration.

        Returns:
            Dict with evaluation result.
        """
        target_path = config.get("target", "package_name")
        include_patterns = config.get("include", [])
        exclude_patterns = config.get("exclude", [])
        case_sensitive = config.get("case_sensitive", True)
        # Default to partial match (search) to make include-only rules intuitive
        full_match = config.get("full_match", False)

        actual_value = self._get_nested_value(facts, target_path)
        if actual_value is None:
            return {
                "decision": "deny",
                "violated_rules": [f"missing target value: {target_path}"],
                "evaluated_metrics": {},
            }

        value_str = str(actual_value)

        # Check exclude patterns first (takes precedence)
        for pattern in exclude_patterns:
            try:
                flags = 0 if case_sensitive else re.IGNORECASE
                if re.search(pattern, value_str, flags):
                    return {
                        "decision": "deny",
                        "violated_rules": [f"excluded by pattern: {pattern}"],
                        "evaluated_metrics": {},
                    }
            except re.error:
                continue

        # Check include patterns if any are specified
        if include_patterns:
            matched = False
            for pattern in include_patterns:
                try:
                    flags = 0 if case_sensitive else re.IGNORECASE
                    if full_match:
                        if re.fullmatch(pattern, value_str, flags):
                            matched = True
                            break
                    else:
                        if re.search(pattern, value_str, flags):
                            matched = True
                            break
                except re.error:
                    continue

            if not matched:
                return {
                    "decision": "deny",
                    "violated_rules": [f"not matched by any include pattern"],
                    "evaluated_metrics": {},
                }

        return {
            "decision": "allow",
            "violated_rules": [],
            "evaluated_metrics": {},
        }

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """Get nested value from dict using dot notation."""
        keys = path.split(".")
        current = data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None

        return current


class LicenseRuleEvaluator(RuleEvaluator):
    """Evaluator for license-based rules."""

    def evaluate(self, facts: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate license rules.

        Args:
            facts: The facts dictionary.
            config: The rule configuration.

        Returns:
            Dict with evaluation result.
        """
        disallowed_licenses = config.get("disallowed_licenses", [])
        allow_unknown = config.get("allow_unknown", False)

        license_id = self._get_nested_value(facts, "license.id")

        if license_id is None:
            if allow_unknown:
                return {
                    "decision": "allow",
                    "violated_rules": [],
                    "evaluated_metrics": {"license.id": None},
                }
            else:
                return {
                    "decision": "deny",
                    "violated_rules": ["license unknown and allow_unknown=false"],
                    "evaluated_metrics": {"license.id": None},
                }

        if license_id in disallowed_licenses:
            return {
                "decision": "deny",
                "violated_rules": [f"license {license_id} is disallowed"],
                "evaluated_metrics": {"license.id": license_id},
            }

        return {
            "decision": "allow",
            "violated_rules": [],
            "evaluated_metrics": {"license.id": license_id},
        }

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """Get nested value from dict using dot notation."""
        keys = path.split(".")
        current = data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None

        return current


class LinkedRuleEvaluator(RuleEvaluator):
    """Evaluator for 'linked' repository policy constraints.

    Configuration options (all optional, defaults shown):
      - enabled: bool = True
      - require_source_repo: bool = False
      - require_version_in_source: bool = False
      - version_tag_patterns: list[str] = ["v{version}", "{version}"]
      - allowed_providers: list[str] = []  # allow all when empty
    """

    def evaluate(self, facts: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
        enabled = config.get("enabled", True)
        require_src = bool(config.get("require_source_repo", False))
        require_ver = bool(config.get("require_version_in_source", False))
        patterns = config.get("version_tag_patterns") or ["v{version}", "{version}"]
        allowed_providers = config.get("allowed_providers") or []

        violations: List[str] = []
        evaluated: Dict[str, Any] = {}

        repo_url = facts.get("source_repo")
        host = facts.get("source_repo_host") or facts.get("repo_host")
        resolved = facts.get("source_repo_resolved")
        exists = facts.get("source_repo_exists")
        version_found = facts.get("version_found_in_source")
        version = facts.get("resolved_version")

        evaluated.update({
            "source_repo": repo_url,
            "source_repo_host": host,
            "source_repo_resolved": resolved,
            "source_repo_exists": exists,
            "resolved_version": version,
            "version_found_in_source": version_found,
        })

        if enabled is False:
            return {
                "decision": "allow",
                "violated_rules": [],
                "evaluated_metrics": evaluated,
            }

        # Provider allow-list enforcement (only when repo is present)
        if allowed_providers:
            if not host:
                violations.append(f"linked: SCM provider not detected; allowed_providers={allowed_providers}")
            elif str(host).lower() not in [p.lower() for p in allowed_providers]:
                violations.append(f"linked: SCM provider '{host}' is not allowed (allowed: {allowed_providers})")

        # Repository presence/resolution/existence
        if require_src:
            if not repo_url:
                violations.append("linked: no source repository URL resolved (require_source_repo=true)")
            else:
                if resolved is not True:
                    violations.append(f"linked: repository URL not normalized/resolved (url={repo_url})")
                if exists is not True:
                    violations.append(f"linked: repository does not exist or is not accessible (url={repo_url})")

        # Version presence in SCM
        if require_ver:
            if version_found is not True:
                pstr = ", ".join(patterns)
                vstr = str(version) if version is not None else "<unknown>"
                rstr = repo_url or "<none>"
                violations.append(
                    f"linked: version not found in SCM (repo={rstr}, version={vstr}, patterns=[{pstr}])"
                )

        decision = "allow" if not violations else "deny"
        return {
            "decision": decision,
            "violated_rules": violations,
            "evaluated_metrics": evaluated,
        }


class RuleEvaluatorRegistry:
    """Registry for rule evaluators."""

    def __init__(self):
        """Initialize the rule evaluator registry."""
        self._evaluators = {
            "metrics": MetricComparatorEvaluator(),
            "regex": RegexRuleEvaluator(),
            "license": LicenseRuleEvaluator(),
            "linked": LinkedRuleEvaluator(),
        }

    def get_evaluator(self, rule_type: str) -> RuleEvaluator:
        """Get a rule evaluator by type.

        Args:
            rule_type: The rule type.

        Returns:
            The rule evaluator instance.

        Raises:
            ValueError: If evaluator not found.
        """
        if rule_type not in self._evaluators:
            raise ValueError(f"Unknown rule type: {rule_type}")
        return self._evaluators[rule_type]

    def register_evaluator(self, rule_type: str, evaluator: RuleEvaluator) -> None:
        """Register a new rule evaluator.

        Args:
            rule_type: The rule type.
            evaluator: The rule evaluator instance.
        """
        self._evaluators[rule_type] = evaluator


# Global registry instance
rule_evaluator_registry = RuleEvaluatorRegistry()
