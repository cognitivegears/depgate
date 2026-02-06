"""Policy evaluator for proxy context."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from analysis.policy import create_policy_engine, PolicyDecision, PolicyEngine
from analysis.facts import FactBuilder
from metapackage import MetaPackage

from .request_parser import RegistryType
from .cache import DecisionCache

logger = logging.getLogger(__name__)


class ProxyEvaluator:
    """Evaluates packages against policy rules in proxy context.

    Wraps the existing PolicyEngine to provide a simpler interface
    for the proxy server, with support for decision caching.
    """

    def __init__(
        self,
        policy_config: Optional[Dict[str, Any]] = None,
        decision_cache: Optional[DecisionCache] = None,
        decision_mode: str = "block",
    ):
        """Initialize the proxy evaluator.

        Args:
            policy_config: Policy configuration dict (from YAML).
            decision_cache: Optional decision cache.
            decision_mode: Mode for handling violations:
                - "block": Return deny decision (403)
                - "warn": Return allow with warnings logged
                - "audit": Return allow, log violations only
        """
        self._policy_config = policy_config or {}
        self._decision_cache = decision_cache
        self._decision_mode = decision_mode
        self._engine: Optional[PolicyEngine] = None
        self._fact_builder: Optional[FactBuilder] = None

    def _ensure_engine(self) -> PolicyEngine:
        """Lazily create the policy engine."""
        if self._engine is None:
            self._engine = create_policy_engine()
        return self._engine

    def _ensure_fact_builder(self) -> FactBuilder:
        """Lazily create the fact builder."""
        if self._fact_builder is None:
            self._fact_builder = FactBuilder()
        return self._fact_builder

    def evaluate(
        self,
        package_name: str,
        version: Optional[str],
        registry_type: RegistryType,
        use_cache: bool = True,
    ) -> PolicyDecision:
        """Evaluate a package against policy rules.

        Args:
            package_name: Package name.
            version: Package version (optional).
            registry_type: Registry type.
            use_cache: Whether to use cached decisions.

        Returns:
            PolicyDecision indicating allow or deny.
        """
        registry = registry_type.value

        # Check cache first
        if use_cache and self._decision_cache:
            cached = self._decision_cache.get(registry, package_name, version)
            if cached:
                logger.debug(f"Cache hit for {registry}:{package_name}:{version}")
                return PolicyDecision(
                    decision=cached.get("decision", "allow"),
                    violated_rules=cached.get("violated_rules", []),
                    evaluated_metrics=cached.get("evaluated_metrics", {}),
                )

        # If no policy config, allow everything
        if not self._policy_config:
            return PolicyDecision(
                decision="allow",
                violated_rules=[],
                evaluated_metrics={},
            )

        # Create a minimal MetaPackage for fact extraction
        # Note: In proxy context, we don't have full package metadata
        # We create a minimal package with what we know
        pkg = self._create_package(package_name, version, registry_type)

        # Build facts
        fact_builder = self._ensure_fact_builder()
        facts = fact_builder.build_facts(pkg)

        # Evaluate policy
        engine = self._ensure_engine()
        decision = engine.evaluate_policy(facts, self._policy_config)

        # Apply decision mode
        final_decision = self._apply_decision_mode(decision)

        # Cache the decision
        if self._decision_cache:
            self._decision_cache.set(
                registry,
                package_name,
                version,
                final_decision.to_dict(),
            )

        return final_decision

    def _create_package(
        self,
        package_name: str,
        version: Optional[str],
        registry_type: RegistryType,
    ) -> MetaPackage:
        """Create a minimal MetaPackage for evaluation.

        In proxy context, we don't fetch full metadata from registries.
        We create a package with the information available from the request.
        """
        # Handle Maven coordinates
        if registry_type == RegistryType.MAVEN and ":" in package_name:
            parts = package_name.split(":")
            if len(parts) == 2:
                pkg = MetaPackage(parts[1], registry_type.value, pkgorg=parts[0])
            else:
                pkg = MetaPackage(package_name, registry_type.value)
        else:
            pkg = MetaPackage(package_name, registry_type.value)

        # Set resolved version if available
        if version:
            pkg.resolved_version = version
            pkg.requested_spec = version

        return pkg

    def _apply_decision_mode(self, decision: PolicyDecision) -> PolicyDecision:
        """Apply decision mode to modify the final decision.

        Args:
            decision: Original policy decision.

        Returns:
            Modified decision based on decision_mode.
        """
        if decision.decision == "allow":
            return decision

        # Handle deny decision based on mode
        if self._decision_mode == "block":
            # Return deny as-is
            return decision
        elif self._decision_mode == "warn":
            # Log warning but allow
            logger.warning(
                f"Policy violation (warn mode): {decision.violated_rules}"
            )
            return PolicyDecision(
                decision="allow",
                violated_rules=decision.violated_rules,
                evaluated_metrics=decision.evaluated_metrics,
            )
        elif self._decision_mode == "audit":
            # Log for audit but allow
            logger.info(f"Policy violation (audit mode): {decision.violated_rules}")
            return PolicyDecision(
                decision="allow",
                violated_rules=decision.violated_rules,
                evaluated_metrics=decision.evaluated_metrics,
            )
        else:
            # Unknown mode, default to block
            return decision

    def set_policy_config(self, config: Dict[str, Any]) -> None:
        """Update the policy configuration.

        Args:
            config: New policy configuration dict.
        """
        self._policy_config = config
        # Clear cache when policy changes
        if self._decision_cache:
            self._decision_cache.clear()

    def set_decision_mode(self, mode: str) -> None:
        """Update the decision mode.

        Args:
            mode: New decision mode ("block", "warn", or "audit").
        """
        if mode not in ("block", "warn", "audit"):
            raise ValueError(f"Invalid decision mode: {mode}")
        self._decision_mode = mode
        if self._decision_cache:
            self._decision_cache.clear()

    def invalidate_cache(
        self,
        registry: Optional[str] = None,
        package_name: Optional[str] = None,
        version: Optional[str] = None,
    ) -> None:
        """Invalidate cached decisions.

        Args:
            registry: Registry type to invalidate.
            package_name: Package name to invalidate.
            version: Specific version to invalidate.
        """
        if self._decision_cache:
            if registry and package_name:
                self._decision_cache.invalidate(registry, package_name, version)
            else:
                self._decision_cache.clear()
