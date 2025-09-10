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
        """
        if not version:
            return ""

        normalized = version.lower()
        suffixes = [".release", ".final", ".ga"]
        for suffix in suffixes:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)]
                break
        return normalized

    def _get_label(self, artifact: Dict[str, Any]) -> str:
        """Extract raw label for matching (preserves 'v', prefixes, etc.)."""
        label = (
            artifact.get("tag_name")
            or artifact.get("name")
            or artifact.get("version")
            or artifact.get("ref")
            or ""
        )
        s = str(label).strip()
        if s.startswith("refs/"):
            s = s.split("/")[-1]
        return s

    def find_match(
        self,
        package_version: str,
        releases_or_tags: Iterable[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Find best match for package version in repository artifacts.

        Strategy order:
          1) exact (raw label equality)
          2) pattern-based (user-provided patterns)
          3) exact-bare (extracted version token equality)
          4) v-prefix (v1.2.3 <-> 1.2.3)
          5) suffix-normalized (e.g., .RELEASE/.Final stripping)
        """
        if not package_version:
            return {
                'matched': False,
                'match_type': None,
                'artifact': None,
                'tag_or_release': None
            }

        artifacts = list(releases_or_tags)

        # 1) Exact (raw label equality)
        exact_label_art = self._find_exact_label_match(package_version, artifacts)
        if exact_label_art:
            label = self._get_label(exact_label_art)
            bare = self._get_version_from_artifact(exact_label_art)
            # Only consider v/bare dual representation as a special-case pair
            pair_exists = self._has_v_bare_pair(artifacts, bare, label)
            tag_or_release = label if pair_exists else bare
            return {
                'matched': True,
                'match_type': 'exact',
                'artifact': exact_label_art,
                'tag_or_release': tag_or_release
            }

        # 2) Pattern-based (use raw labels, not normalized)
        for pattern in self.patterns:
            pat_art = self._find_pattern_match(package_version, artifacts, pattern)
            if pat_art:
                return {
                    'matched': True,
                    'match_type': 'pattern',
                    'artifact': pat_art,
                    'tag_or_release': self._get_label(pat_art)
                }

        # 3) Exact-bare (extracted version token equality, only when query is bare)
        exact_bare_art = self._find_exact_bare_match(package_version, artifacts)
        if exact_bare_art:
            return {
                'matched': True,
                'match_type': 'exact',
                'artifact': exact_bare_art,
                'tag_or_release': self._get_version_from_artifact(exact_bare_art)
            }

        # 4) v-prefix
        v_pref_art = self._find_v_prefix_match(package_version, artifacts)
        if v_pref_art:
            return {
                'matched': True,
                'match_type': 'v-prefix',
                'artifact': v_pref_art,
                'tag_or_release': self._get_label(v_pref_art)
            }

        # 5) Suffix-normalized (e.g., 1.0.0.RELEASE -> 1.0.0)
        norm_art = self._find_normalized_match(package_version, artifacts)
        if norm_art:
            return {
                'matched': True,
                'match_type': 'suffix-normalized',
                'artifact': norm_art,
                'tag_or_release': self._get_version_from_artifact(norm_art)
            }

        return {
            'matched': False,
            'match_type': None,
            'artifact': None,
            'tag_or_release': None
        }

    def _find_exact_label_match(
        self,
        package_version: str,
        artifacts: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Find exact match using raw label equality only."""
        pv = package_version.strip()
        for artifact in artifacts:
            if self._get_label(artifact) == pv:
                return artifact
        return None

    def _has_v_bare_pair(self, artifacts: List[Dict[str, Any]], bare: str, current_label: str) -> bool:
        """Check if both 'v{bare}' and '{bare}' labels exist among artifacts (excluding current)."""
        v_label = f"v{bare}"
        for a in artifacts:
            label = self._get_label(a)
            if label != current_label and (label == bare or label == v_label):
                return True
        return False

    def _find_exact_bare_match(
        self,
        package_version: str,
        artifacts: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Find exact match using extracted bare version equality.

        Only applies when the query itself is bare (does not start with 'v') to
        avoid reclassifying v-prefix cases as exact.
        """
        pv = package_version.strip()
        if pv.startswith('v'):
            return None
        for artifact in artifacts:
            artifact_version = self._get_version_from_artifact(artifact)
            if artifact_version == pv:
                return artifact
        return None

    def _find_v_prefix_match(
        self,
        package_version: str,
        artifacts: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """Find match with v-prefix variations."""
        for artifact in artifacts:
            artifact_version = self._get_version_from_artifact(artifact)
            # Handle v-prefix variations: v1.0.0 matches 1.0.0, and 1.0.0 matches v1.0.0
            if (package_version.startswith('v') and artifact_version == package_version[1:]) or \
               (artifact_version.startswith('v') and package_version == artifact_version[1:]):
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
        """Find match using custom pattern against raw labels."""
        try:
            regex_pattern = pattern.replace("<v>", re.escape(package_version))
            compiled_pattern = re.compile(regex_pattern, re.IGNORECASE)
            for artifact in artifacts:
                label = self._get_label(artifact)
                if compiled_pattern.match(label):
                    return artifact
        except re.error:
            # Invalid pattern, skip
            pass
        return None

    def _get_version_from_artifact(self, artifact: Dict[str, Any]) -> str:
        """Extract version-like token from artifact dict.

        Handles common forms:
        - tag_name/name: 'v1.2.3', '1.2.3'
        - monorepo: 'react-router@1.2.3'
        - hyphen/underscore: 'react-router-1.2.3', 'react_router_1.2.3'
        - refs: 'refs/tags/v1.2.3', 'refs/tags/react-router@1.2.3'
        """
        def _extract_semverish(s: str) -> str:
            s = s.strip()
            # Collapse refs/tags/... to terminal segment
            if '/' in s and s.startswith("refs/"):
                s = s.split('/')[-1]
            # Split monorepo form package@version
            if '@' in s:
                tail = s.rsplit('@', 1)[1]
                if any(ch.isdigit() for ch in tail):
                    s = tail
            # Try to pull a trailing version-ish token (optional 'v' + 2-4 dot parts + optional pre/build)
            m = re.search(r'v?(\d+(?:\.\d+){1,3}(?:[-+][0-9A-Za-z.\-]+)?)$', s)
            if m:
                return m.group(1)  # return without leading 'v' to favor exact equality
            return s

        # Prefer tag_name over display name; then explicit version; finally ref
        v = artifact.get('tag_name')
        if v:
            return _extract_semverish(str(v))

        v = artifact.get('name')
        if v:
            return _extract_semverish(str(v))

        v = artifact.get('version')
        if v:
            return _extract_semverish(str(v))

        v = artifact.get('ref')
        if v:
            return _extract_semverish(str(v))

        return ""
