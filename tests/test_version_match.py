"""Unit tests for version matching utilities."""
from __future__ import annotations

import pytest

from repository.version_match import VersionMatcher


class TestVersionMatcher:
    """Test cases for VersionMatcher class."""

    def test_normalize_version_basic(self):
        """Test basic version normalization."""
        matcher = VersionMatcher()
        assert matcher.normalize_version("1.0.0") == "1.0.0"
        assert matcher.normalize_version("v1.0.0") == "v1.0.0"

    def test_normalize_version_maven_suffixes(self):
        """Test Maven suffix stripping."""
        matcher = VersionMatcher()
        assert matcher.normalize_version("1.0.0.RELEASE") == "1.0.0"
        assert matcher.normalize_version("1.0.0.Final") == "1.0.0"
        assert matcher.normalize_version("1.0.0.GA") == "1.0.0"

    def test_normalize_version_case_preservation(self):
        """Test case preservation in normalization."""
        matcher = VersionMatcher()
        assert matcher.normalize_version("1.0.0-SNAPSHOT") == "1.0.0-snapshot"

    def test_normalize_version_empty(self):
        """Test empty version normalization."""
        matcher = VersionMatcher()
        assert matcher.normalize_version("") == ""

    def test_find_match_exact(self):
        """Test exact version match."""
        matcher = VersionMatcher()
        artifacts = [
            {"name": "v1.0.0", "tag_name": "v1.0.0"},
            {"name": "v1.1.0", "tag_name": "v1.1.0"}
        ]

        result = matcher.find_match("v1.0.0", artifacts)
        assert result["matched"] is True
        assert result["match_type"] == "exact"
        assert result["tag_or_release"] == "1.0.0"

    def test_find_match_v_prefix(self):
        """Test v-prefix version match."""
        matcher = VersionMatcher()
        artifacts = [
            {"name": "1.0.0", "tag_name": "1.0.0"}
        ]

        result = matcher.find_match("v1.0.0", artifacts)
        assert result["matched"] is True
        assert result["match_type"] == "v-prefix"
        assert result["tag_or_release"] == "1.0.0"

    def test_find_match_suffix_normalized(self):
        """Test suffix-normalized version match."""
        matcher = VersionMatcher()
        artifacts = [
            {"name": "1.0.0", "tag_name": "1.0.0"}
        ]

        result = matcher.find_match("1.0.0.RELEASE", artifacts)
        assert result["matched"] is True
        assert result["match_type"] == "suffix-normalized"
        assert result["tag_or_release"] == "1.0.0"

    def test_find_match_pattern(self):
        """Test pattern-based version match."""
        matcher = VersionMatcher(patterns=["release-<v>"])
        artifacts = [
            {"name": "release-1.0.0", "tag_name": "release-1.0.0"}
        ]

        result = matcher.find_match("1.0.0", artifacts)
        assert result["matched"] is True
        assert result["match_type"] == "pattern"
        assert result["tag_or_release"] == "release-1.0.0"

    def test_find_match_no_match(self):
        """Test no match found."""
        matcher = VersionMatcher()
        artifacts = [
            {"name": "v2.0.0", "tag_name": "v2.0.0"}
        ]

        result = matcher.find_match("v1.0.0", artifacts)
        assert result["matched"] is False
        assert result["match_type"] is None
        assert result["artifact"] is None

    def test_find_match_empty_artifacts(self):
        """Test matching with empty artifacts list."""
        matcher = VersionMatcher()
        result = matcher.find_match("v1.0.0", [])
        assert result["matched"] is False

    def test_find_match_empty_version(self):
        """Test matching with empty version."""
        matcher = VersionMatcher()
        artifacts = [{"name": "v1.0.0", "tag_name": "v1.0.0"}]
        result = matcher.find_match("", artifacts)
        assert result["matched"] is False

    def test_find_match_first_found(self):
        """Test that first match is returned when multiple exist."""
        matcher = VersionMatcher()
        artifacts = [
            {"name": "v1.0.0", "tag_name": "v1.0.0"},
            {"name": "1.0.0", "tag_name": "1.0.0"}  # Also matches v1.0.0
        ]

        result = matcher.find_match("v1.0.0", artifacts)
        assert result["matched"] is True
        assert result["tag_or_release"] == "v1.0.0"  # First match

    def test_pattern_with_invalid_regex(self):
        """Test handling of invalid regex patterns."""
        matcher = VersionMatcher(patterns=["invalid[regex"])
        artifacts = [{"name": "test", "tag_name": "test"}]

        # Should not crash, just skip invalid pattern
        result = matcher.find_match("1.0.0", artifacts)
        assert result["matched"] is False

    def test_multiple_patterns(self):
        """Test multiple patterns with first match winning."""
        matcher = VersionMatcher(patterns=["tag-<v>", "release-<v>"])
        artifacts = [
            {"name": "tag-1.0.0", "tag_name": "tag-1.0.0"},
            {"name": "release-1.0.0", "tag_name": "release-1.0.0"}
        ]

        result = matcher.find_match("1.0.0", artifacts)
        assert result["matched"] is True
        assert result["tag_or_release"] == "tag-1.0.0"  # First pattern matches first

    def test_artifact_version_extraction(self):
        """Test version extraction from different artifact formats."""
        matcher = VersionMatcher()

        # Test name field - normalized to bare version
        artifact1 = {"name": "v1.0.0"}
        assert matcher._get_version_from_artifact(artifact1) == "1.0.0"

        # Test tag_name field - normalized to bare version
        artifact2 = {"tag_name": "v1.0.0"}
        assert matcher._get_version_from_artifact(artifact2) == "1.0.0"

        # Test version field
        artifact3 = {"version": "1.0.0"}
        assert matcher._get_version_from_artifact(artifact3) == "1.0.0"

        # Test ref field - normalized to bare version
        artifact4 = {"ref": "refs/tags/v1.0.0"}
        assert matcher._get_version_from_artifact(artifact4) == "1.0.0"

        # Test monorepo tag format
        artifact5 = {"tag_name": "react-router@7.8.2"}
        assert matcher._get_version_from_artifact(artifact5) == "7.8.2"

        # Test hyphen form
        artifact6 = {"name": "react-router-7.8.2"}
        assert matcher._get_version_from_artifact(artifact6) == "7.8.2"

        # Test underscore form
        artifact7 = {"name": "react_router_7.8.2"}
        assert matcher._get_version_from_artifact(artifact7) == "7.8.2"

        # Test ref with monorepo
        artifact8 = {"ref": "refs/tags/react-router@7.8.2"}
        assert matcher._get_version_from_artifact(artifact8) == "7.8.2"

        # Test empty artifact
        artifact9 = {}
        assert matcher._get_version_from_artifact(artifact9) == ""

    def test_find_match_monorepo_artifacts(self):
        """Test matching with monorepo-style artifact names."""
        matcher = VersionMatcher()
        artifacts = [
            {"name": "react-router@7.8.2", "tag_name": "react-router@7.8.2"},
            {"name": "react-router-7.8.2", "tag_name": "react-router-7.8.2"},
            {"name": "react_router_7.8.2", "tag_name": "react_router_7.8.2"}
        ]

        result = matcher.find_match("7.8.2", artifacts)
        assert result["matched"] is True
        assert result["match_type"] == "exact"
        assert result["tag_or_release"] == "7.8.2"

    def test_find_match_normalized_v_prefix(self):
        """Test that v-prefix artifacts are normalized for matching."""
        matcher = VersionMatcher()
        artifacts = [
            {"name": "v1.0.0", "tag_name": "v1.0.0"}
        ]

        # Should match both "1.0.0" and "v1.0.0" queries
        result1 = matcher.find_match("1.0.0", artifacts)
        assert result1["matched"] is True
        assert result1["match_type"] == "exact"
        assert result1["tag_or_release"] == "1.0.0"

        result2 = matcher.find_match("v1.0.0", artifacts)
        assert result2["matched"] is True
        assert result2["match_type"] == "exact"
        assert result2["tag_or_release"] == "1.0.0"
