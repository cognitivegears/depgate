"""Facts model and builder for policy analysis."""

from typing import Dict, Any, Optional, List
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
        return {
            "package_name": package.pkg_name,
            "registry": package.pkg_type,
            "source_repo": getattr(package, "repo_url_normalized", None),
            "stars_count": getattr(package, "repo_stars", None),
            "contributors_count": getattr(package, "repo_contributors", None),
            "version_count": getattr(package, "version_count", None),
            "release_found_in_source_registry": getattr(package, "repo_present_in_registry", None),
            "heuristic_score": getattr(package, "score", None),
            "license": {
                "id": getattr(package, "license_id", None),
                "available": getattr(package, "license_available", None),
                "source": getattr(package, "license_source", None)
            }
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
