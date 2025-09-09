"""Tests for token parsing functionality."""

import pytest

from src.versioning.models import Ecosystem, ResolutionMode
from src.versioning.parser import parse_cli_token, parse_manifest_entry, tokenize_rightmost_colon


class TestTokenizeRightmostColon:
    """Test tokenize_rightmost_colon function."""

    def test_no_colon(self):
        assert tokenize_rightmost_colon("left-pad") == ("left-pad", None)

    def test_single_colon(self):
        assert tokenize_rightmost_colon("left-pad:^1.3.0") == ("left-pad", "^1.3.0")

    def test_whitespace_stripping(self):
        assert tokenize_rightmost_colon("  lodash : 4.17.21  ") == ("lodash", "4.17.21")

    def test_trailing_colon(self):
        assert tokenize_rightmost_colon("a:b:") == ("a:b", None)

    def test_multiple_colons(self):
        assert tokenize_rightmost_colon("g:a:1.2.3") == ("g:a", "1.2.3")

    def test_empty_spec_after_colon(self):
        assert tokenize_rightmost_colon("package:") == ("package", None)

    def test_only_colon(self):
        assert tokenize_rightmost_colon(":") == ("", None)


class TestParseCliToken:
    """Test parse_cli_token function."""

    def test_npm_exact_version(self):
        req = parse_cli_token("lodash:4.17.21", Ecosystem.NPM)
        assert req.ecosystem == Ecosystem.NPM
        assert req.identifier == "lodash"
        assert req.requested_spec.raw == "4.17.21"
        assert req.requested_spec.mode == ResolutionMode.EXACT
        assert req.requested_spec.include_prerelease == False
        assert req.source == "cli"
        assert req.raw_token == "lodash:4.17.21"

    def test_npm_range_version(self):
        req = parse_cli_token("left-pad:^1.3.0", Ecosystem.NPM)
        assert req.identifier == "left-pad"
        assert req.requested_spec.raw == "^1.3.0"
        assert req.requested_spec.mode == ResolutionMode.RANGE
        assert req.requested_spec.include_prerelease == False

    def test_npm_scoped_package(self):
        req = parse_cli_token("@types/node:^18.0.0", Ecosystem.NPM)
        assert req.identifier == "@types/node"
        assert req.requested_spec.raw == "^18.0.0"
        assert req.requested_spec.mode == ResolutionMode.RANGE
        assert req.requested_spec.include_prerelease == False

    def test_npm_latest(self):
        req = parse_cli_token("express", Ecosystem.NPM)
        assert req.identifier == "express"
        assert req.requested_spec is None
        assert req.source == "cli"

    def test_npm_explicit_latest(self):
        req = parse_cli_token("left-pad:latest", Ecosystem.NPM)
        assert req.identifier == "left-pad"
        assert req.requested_spec is None

    def test_npm_prerelease(self):
        req = parse_cli_token("package:1.0.0-rc.1", Ecosystem.NPM)
        assert req.requested_spec.include_prerelease == True

    def test_pypi_exact_version(self):
        req = parse_cli_token("toml:3.0.0", Ecosystem.PYPI)
        assert req.ecosystem == Ecosystem.PYPI
        assert req.identifier == "toml"
        assert req.requested_spec.raw == "3.0.0"
        assert req.requested_spec.mode == ResolutionMode.EXACT
        assert req.requested_spec.include_prerelease == False

    def test_pypi_range_version(self):
        req = parse_cli_token("packaging:>=21.0", Ecosystem.PYPI)
        assert req.identifier == "packaging"
        assert req.requested_spec.raw == ">=21.0"
        assert req.requested_spec.mode == ResolutionMode.RANGE
        assert req.requested_spec.include_prerelease == False

    def test_pypi_normalization(self):
        req = parse_cli_token("Requests", Ecosystem.PYPI)
        assert req.identifier == "requests"
        assert req.requested_spec is None

    def test_pypi_underscore_to_hyphen(self):
        req = parse_cli_token("python_dateutil:2.8.0", Ecosystem.PYPI)
        assert req.identifier == "python-dateutil"

    def test_maven_exact_version(self):
        req = parse_cli_token("org.apache.commons:commons-lang3:3.12.0", Ecosystem.MAVEN)
        assert req.ecosystem == Ecosystem.MAVEN
        assert req.identifier == "org.apache.commons:commons-lang3"
        assert req.requested_spec.raw == "3.12.0"
        assert req.requested_spec.mode == ResolutionMode.EXACT
        assert req.requested_spec.include_prerelease == False

    def test_maven_latest(self):
        req = parse_cli_token("org.group:artifact", Ecosystem.MAVEN)
        assert req.identifier == "org.group:artifact"
        assert req.requested_spec is None

    def test_maven_snapshot(self):
        req = parse_cli_token("a:b:SNAPSHOT", Ecosystem.MAVEN)
        assert req.identifier == "a:b"
        assert req.requested_spec.raw == "SNAPSHOT"
        assert req.requested_spec.mode == ResolutionMode.EXACT
        assert req.requested_spec.include_prerelease == False

    def test_maven_three_colons(self):
        req = parse_cli_token("g:a:1.2.3", Ecosystem.MAVEN)
        assert req.identifier == "g:a"
        assert req.requested_spec.raw == "1.2.3"
        assert req.requested_spec.mode == ResolutionMode.EXACT


class TestParseManifestEntry:
    """Test parse_manifest_entry function."""

    def test_pypi_manifest_exact(self):
        req = parse_manifest_entry("toml", "3.0.0", Ecosystem.PYPI, "manifest")
        assert req.ecosystem == Ecosystem.PYPI
        assert req.identifier == "toml"
        assert req.requested_spec.raw == "3.0.0"
        assert req.requested_spec.mode == ResolutionMode.EXACT
        assert req.requested_spec.include_prerelease == False
        assert req.source == "manifest"
        assert req.raw_token is None

    def test_pypi_manifest_range(self):
        req = parse_manifest_entry("packaging", ">=21.0", Ecosystem.PYPI, "manifest")
        assert req.identifier == "packaging"
        assert req.requested_spec.raw == ">=21.0"
        assert req.requested_spec.mode == ResolutionMode.RANGE
        assert req.requested_spec.include_prerelease == False

    def test_pypi_manifest_prerelease_spec(self):
        req = parse_manifest_entry("pydantic", "~=2.0", Ecosystem.PYPI, "manifest")
        assert req.identifier == "pydantic"
        assert req.requested_spec.raw == "~=2.0"
        assert req.requested_spec.mode == ResolutionMode.RANGE
        assert req.requested_spec.include_prerelease == False

    def test_manifest_empty_spec(self):
        req = parse_manifest_entry("package", "", Ecosystem.PYPI, "manifest")
        assert req.requested_spec is None

    def test_manifest_latest_spec(self):
        req = parse_manifest_entry("package", "latest", Ecosystem.PYPI, "manifest")
        assert req.requested_spec is None

    def test_manifest_none_spec(self):
        req = parse_manifest_entry("package", None, Ecosystem.PYPI, "manifest")
        assert req.requested_spec is None
