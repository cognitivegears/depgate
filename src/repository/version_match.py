"""Version normalization and matching utilities.

Provides utilities for normalizing package versions and finding matches
against repository tags and releases.
"""
from __future__ import annotations

import re
from typing import List, Optional, Dict, Any, Iterable


class VersionMatcher:
    """Handles version normalization and matching against repository artifacts.

    Supports various matching strategies: exact, v-prefix, suffix-normalized,
    and pattern-based matching.
    """

    def __init__(self, patterns: Optional[List[str]] = None):
        """Initialize version matcher with optional custom patterns.

        Args:
            patterns: List of regex patterns for version matching (e.g., ["release-<v>"])
        """
        self.patterns = patterns or []

    def normalize_version(self, version: str) -> str:
        """Normalize version string for consistent matching.

        Strips common Maven suffixes (.RELEASE, .Final) and returns
        lowercase semantic version string without coercing numerics.

        Args:
            version: Version string to normalize

        Returns:
            Normalized version string
        """
        if not version:
            return ""

        # Convert to lowercase
        normalized = version.lower()

        # Strip common Maven suffixes
        suffixes = [".release", ".final", ".ga"]
        for suffix in suffixes:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)]
                break

        return normalized

    def find_match(
        self,
        package_version: str,
        releases_or_tags: Iterable[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Find best match for package version in repository artifacts.

        Tries matching strategies in order: exact, v-prefix, suffix-normalized, pattern.
        Returns first match found.

        Args:
            package_version: Package version to match
            releases_or_tags: Iterable of release/tag dictionaries

        Returns:
            Dict with match details or None if no match found
        """
        if not package_version:
            return {
                'matched': False,
                'match_type': None,
                'artifact': None,
                'tag_or_release': None
            }

        # Convert to list for multiple iterations
        artifacts = list(releases_or_tags)

        # Try exact match first
        exact_match = self._find_exact_match(package_version, artifacts)
        if exact_match:
            return {
                'matched': True,
                'match_type': 'exact',
                'artifact': exact_match,
                'tag_or_release': self._get_version_from_artifact(exact_match)
            }

        # Try v-prefix match
        v_prefix_match = self._find_v_prefix_match(package_version, artifacts)
        if v_prefix_match:
            return {
                'matched': True,
                'match_type': 'v-prefix',
                'artifact': v_prefix_match,
                'tag_or_release': self._get_version_from_artifact(v_prefix_match)
            }

        # Try suffix-normalized match
        normalized_match = self._find_normalized_match(package_version, artifacts)
        if normalized_match:
            return {
                'matched': True,
                'match_type': 'suffix-normalized',
                'artifact': normalized_match,
                'tag_or_release': self._get_version_from_artifact(normalized_match)
            }

        # Try pattern matches
        for pattern in self.patterns:
            pattern_match = self._find_pattern_match(package_version, artifacts, pattern)
            if pattern_match:
                return {
                    'matched': True,
                    'match_type': 'pattern',
                    'artifact': pattern_match,
                    'tag_or_release': self._get_version_from_artifact(pattern_match)
                }

        return {
            'matched': False,
            'match_type': None,
            'artifact': None,
            'tag_or_release': None
        }

    def _find_exact_match(
        self,
        package_version: str,
        artifacts: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Find exact version match."""
        for artifact in artifacts:
            artifact_version = self._get_version_from_artifact(artifact)
            if artifact_version == package_version:
                return artifact
        return None

    def _find_v_prefix_match(
        self,
        package_version: str,
        artifacts: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Find match with v-prefix (e.g., v1.0.0 matches 1.0.0)."""
        # If package version starts with 'v', look for version without 'v'
        if package_version.startswith('v'):
            base_version = package_version[1:]
            for artifact in artifacts:
                artifact_version = self._get_version_from_artifact(artifact)
                if artifact_version == base_version:
                    return artifact
        return None

    def _find_normalized_match(
        self,
        package_version: str,
        artifacts: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Find match using normalized versions."""
        normalized_package = self.normalize_version(package_version)
        for artifact in artifacts:
            artifact_version = self._get_version_from_artifact(artifact)
            normalized_artifact = self.normalize_version(artifact_version)
            if normalized_artifact == normalized_package:
                return artifact
        return None

    def _find_pattern_match(
        self,
        package_version: str,
        artifacts: List[Dict[str, Any]],
        pattern: str
    ) -> Optional[Dict[str, Any]]:
        """Find match using custom pattern."""
        try:
            # Replace <v> placeholder with package version
            regex_pattern = pattern.replace("<v>", re.escape(package_version))
            compiled_pattern = re.compile(regex_pattern, re.IGNORECASE)

            for artifact in artifacts:
                artifact_version = self._get_version_from_artifact(artifact)
                if compiled_pattern.match(artifact_version):
                    return artifact
        except re.error:
            # Invalid pattern, skip
            pass

        return None

    def _get_version_from_artifact(self, artifact: Dict[str, Any]) -> str:
        """Extract version string from artifact dict.

        Handles different formats from GitHub/GitLab APIs.
        """
        # Try common keys
        for key in ['name', 'tag_name', 'version', 'ref']:
            if key in artifact and artifact[key]:
                return str(artifact[key])

        return ""
