"""Facts model and builder for policy analysis."""

from typing import Dict, Any, List
from metapackage import MetaPackage


class FactBuilder:
    """Builder for creating unified facts from MetaPackage instances."""

    def __init__(self):
        """Initialize the FactBuilder."""
        self._extractors: List[MetricExtractor] = []

    def add_extractor(self, extractor: 'MetricExtractor') -> None:
        """Add a metric extractor to the builder.

        Args:
            extractor: The metric extractor to add.
        """
        self._extractors.append(extractor)

    def build_facts(self, package: MetaPackage) -> Dict[str, Any]:
        """Build facts dictionary from a MetaPackage instance.

        Args:
            package: The MetaPackage instance to extract facts from.

        Returns:
            Dict containing the unified facts.
        """
        facts = self._extract_base_facts(package)

        # Apply metric extractors
        for extractor in self._extractors:
            try:
                additional_facts = extractor.extract(package)
                facts.update(additional_facts)
            except Exception:
                # Skip failed extractions
                continue

        return facts

    def _extract_base_facts(self, package: MetaPackage) -> Dict[str, Any]:
        """Extract base facts from MetaPackage.

        Args:
            package: The MetaPackage instance.

        Returns:
            Dict containing base facts.
        """
        # Compute derived repo/version facts for policy consumption
        try:
            vm = getattr(package, "repo_version_match", None)
            version_found_in_source = bool(vm.get("matched", False)) if isinstance(vm, dict) else None
        except Exception:  # pylint: disable=broad-exception-caught
            version_found_in_source = None

        return {
            "package_name": package.pkg_name,
            "registry": package.pkg_type,
            "source_repo": getattr(package, "repo_url_normalized", None),
            "source_repo_resolved": getattr(package, "repo_resolved", None),
            "source_repo_exists": getattr(package, "repo_exists", None),
            "source_repo_host": getattr(package, "repo_host", None),
            "resolved_version": getattr(package, "resolved_version", None),
            "version_found_in_source": version_found_in_source,
            "stars_count": getattr(package, "repo_stars", None),
            "contributors_count": getattr(package, "repo_contributors", None),
            "version_count": getattr(package, "version_count", None),
            "weekly_downloads": getattr(package, "weekly_downloads", None),
            "forks_count": getattr(package, "repo_forks", None),
            "open_issues_count": getattr(package, "repo_open_issues", None),
            "open_prs_count": getattr(package, "repo_open_prs", None),
            "last_commit_at": getattr(package, "repo_last_commit_at", None),
            "last_merged_pr_at": getattr(package, "repo_last_merged_pr_at", None),
            "last_closed_issue_at": getattr(package, "repo_last_closed_issue_at", None),
            "release_found_in_source_registry": getattr(package, "repo_present_in_registry", None),
            "release_age_days": getattr(package, "release_age_days", None),
            "heuristic_score": getattr(package, "score", None),
            "supply_chain_trust_score": getattr(package, "trust_score", None),
            "supply_chain_previous_trust_score": getattr(package, "previous_trust_score", None),
            "supply_chain_trust_score_delta": getattr(package, "trust_score_delta", None),
            "supply_chain_trust_score_decreased": getattr(package, "trust_score_decreased", None),
            "provenance_present": getattr(package, "provenance_present", None),
            "previous_provenance_present": getattr(package, "previous_provenance_present", None),
            "provenance_regressed": getattr(package, "provenance_regressed", None),
            "registry_signature_present": getattr(package, "registry_signature_present", None),
            "previous_registry_signature_present": getattr(package, "previous_registry_signature_present", None),
            "registry_signature_regressed": getattr(package, "registry_signature_regressed", None),
            "checksums_present": getattr(package, "checksums_present", None),
            "previous_checksums_present": getattr(package, "previous_checksums_present", None),
            "previous_release_version": getattr(package, "previous_release_version", None),
            "license": {
                "id": getattr(package, "license_id", None),
                "available": getattr(package, "license_available", None),
                "source": getattr(package, "license_source", None)
            },
            "osm_malicious": getattr(package, "osm_malicious", None),
            "osm_reason": getattr(package, "osm_reason", None),
            "osm_threat_count": getattr(package, "osm_threat_count", None),
            "osm_severity": getattr(package, "osm_severity", None),
        }


class MetricExtractor:
    """Base class for metric extractors."""

    def extract(self, package: MetaPackage) -> Dict[str, Any]:
        """Extract metrics from a package.

        Args:
            package: The MetaPackage instance.

        Returns:
            Dict containing extracted metrics.
        """
        raise NotImplementedError
