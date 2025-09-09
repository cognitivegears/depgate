"""Tests for Maven version resolver."""

import json
from typing import Optional
from unittest.mock import patch

import pytest

from src.versioning.cache import TTLCache
from src.versioning.models import Ecosystem, PackageRequest, ResolutionMode, VersionSpec
from src.versioning.resolvers.maven import MavenVersionResolver


@pytest.fixture
def cache():
    """Create a fresh cache for each test."""
    return TTLCache()


@pytest.fixture
def resolver(cache):
    """Create Maven resolver with cache."""
    return MavenVersionResolver(cache)


def create_request(identifier: str, spec_raw: Optional[str] = None, mode: Optional[ResolutionMode] = None) -> PackageRequest:
    """Helper to create package requests."""
    spec = None
    if spec_raw:
        spec = VersionSpec(raw=spec_raw, mode=mode or ResolutionMode.RANGE, include_prerelease=False)

    return PackageRequest(
        ecosystem=Ecosystem.MAVEN,
        identifier=identifier,
        requested_spec=spec,
        source="test",
        raw_token=f"{identifier}:{spec_raw}" if spec_raw else identifier
    )


class TestMavenVersionResolver:
    """Test Maven version resolver functionality."""

    @patch('src.versioning.resolvers.maven.robust_get')
    def test_exact_version_present(self, mock_robust_get, resolver):
        """Test exact version match when version exists."""
        mock_robust_get.return_value = (200, {}, """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <groupId>com.example</groupId>
  <artifactId>test</artifactId>
  <versioning>
    <versions>
      <version>1.0.0</version>
      <version>1.1.0</version>
      <version>2.0.0</version>
    </versions>
  </versioning>
</metadata>""")

        req = create_request("com.example:test", "1.1.0", ResolutionMode.EXACT)
        version, count, error = resolver.pick(req, ["1.0.0", "1.1.0", "2.0.0"])

        assert version == "1.1.0"
        assert count == 3
        assert error is None

    @patch('src.versioning.resolvers.maven.robust_get')
    def test_exact_version_not_found(self, mock_robust_get, resolver):
        """Test exact version when version doesn't exist."""
        mock_robust_get.return_value = (200, {}, """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <groupId>com.example</groupId>
  <artifactId>test</artifactId>
  <versioning>
    <versions>
      <version>1.0.0</version>
      <version>1.1.0</version>
      <version>2.0.0</version>
    </versions>
  </versioning>
</metadata>""")

        req = create_request("com.example:test", "1.2.0", ResolutionMode.EXACT)
        version, count, error = resolver.pick(req, ["1.0.0", "1.1.0", "2.0.0"])

        assert version is None
        assert count == 3
        assert "not found" in error

    @patch('src.versioning.resolvers.maven.robust_get')
    def test_bracket_range_inclusive(self, mock_robust_get, resolver):
        """Test bracket range [1.0,2.0) selects highest in inclusive-exclusive range."""
        mock_robust_get.return_value = (200, {}, """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <groupId>com.example</groupId>
  <artifactId>test</artifactId>
  <versioning>
    <versions>
      <version>0.9.0</version>
      <version>1.0.0</version>
      <version>1.5.0</version>
      <version>2.0.0</version>
      <version>2.1.0</version>
    </versions>
  </versioning>
</metadata>""")

        req = create_request("com.example:test", "[1.0,2.0)", ResolutionMode.RANGE)
        version, count, error = resolver.pick(req, ["0.9.0", "1.0.0", "1.5.0", "2.0.0", "2.1.0"])

        assert version == "1.5.0"  # Highest in [1.0,2.0)
        assert count == 5
        assert error is None

    @patch('src.versioning.resolvers.maven.robust_get')
    def test_bracket_range_exclusive_upper(self, mock_robust_get, resolver):
        """Test bracket range (1.0,2.0] excludes lower bound, includes upper."""
        mock_robust_get.return_value = (200, {}, """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <groupId>com.example</groupId>
  <artifactId>test</artifactId>
  <versioning>
    <versions>
      <version>1.0.0</version>
      <version>1.5.0</version>
      <version>2.0.0</version>
      <version>2.1.0</version>
    </versions>
  </versioning>
</metadata>""")

        req = create_request("com.example:test", "(1.0,2.0]", ResolutionMode.RANGE)
        version, count, error = resolver.pick(req, ["1.0.0", "1.5.0", "2.0.0", "2.1.0"])

        assert version == "2.0.0"  # Highest in (1.0,2.0]
        assert count == 4
        assert error is None

    @patch('src.versioning.resolvers.maven.robust_get')
    def test_single_version_bracket(self, mock_robust_get, resolver):
        """Test single version bracket [1.2] exact match."""
        mock_robust_get.return_value = (200, {}, """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <groupId>com.example</groupId>
  <artifactId>test</artifactId>
  <versioning>
    <versions>
      <version>1.0.0</version>
      <version>1.2.0</version>
      <version>1.5.0</version>
    </versions>
  </versioning>
</metadata>""")

        req = create_request("com.example:test", "[1.2]", ResolutionMode.RANGE)
        version, count, error = resolver.pick(req, ["1.0.0", "1.2.0", "1.5.0"])

        assert version == "1.2.0"
        assert count == 3
        assert error is None

    @patch('src.versioning.resolvers.maven.robust_get')
    def test_open_ended_range(self, mock_robust_get, resolver):
        """Test open-ended range (,1.0] selects versions <= 1.0."""
        mock_robust_get.return_value = (200, {}, """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <groupId>com.example</groupId>
  <artifactId>test</artifactId>
  <versioning>
    <versions>
      <version>0.5.0</version>
      <version>0.8.0</version>
      <version>1.0.0</version>
      <version>1.1.0</version>
    </versions>
  </versioning>
</metadata>""")

        req = create_request("com.example:test", "(,1.0]", ResolutionMode.RANGE)
        version, count, error = resolver.pick(req, ["0.5.0", "0.8.0", "1.0.0", "1.1.0"])

        assert version == "1.0.0"  # Highest <= 1.0
        assert count == 4
        assert error is None

    @patch('src.versioning.resolvers.maven.robust_get')
    def test_latest_mode_excludes_snapshot(self, mock_robust_get, resolver):
        """Test latest mode selects highest stable version, excludes SNAPSHOT."""
        mock_robust_get.return_value = (200, {}, """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <groupId>com.example</groupId>
  <artifactId>test</artifactId>
  <versioning>
    <versions>
      <version>1.0.0</version>
      <version>1.1.0</version>
      <version>2.0.0-SNAPSHOT</version>
      <version>1.9.9</version>
    </versions>
  </versioning>
</metadata>""")

        req = create_request("com.example:test")  # No spec = latest
        version, count, error = resolver.pick(req, ["1.0.0", "1.1.0", "2.0.0-SNAPSHOT", "1.9.9"])

        assert version == "1.9.9"  # Highest stable, excludes SNAPSHOT
        assert count == 4
        assert error is None

    @patch('src.versioning.resolvers.maven.robust_get')
    def test_exact_snapshot_allowed(self, mock_robust_get, resolver):
        """Test exact SNAPSHOT version is allowed when explicitly requested."""
        mock_robust_get.return_value = (200, {}, """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <groupId>com.example</groupId>
  <artifactId>test</artifactId>
  <versioning>
    <versions>
      <version>1.0.0</version>
      <version>2.0.0-SNAPSHOT</version>
    </versions>
  </versioning>
</metadata>""")

        req = create_request("com.example:test", "2.0.0-SNAPSHOT", ResolutionMode.EXACT)
        version, count, error = resolver.pick(req, ["1.0.0", "2.0.0-SNAPSHOT"])

        assert version == "2.0.0-SNAPSHOT"
        assert count == 2
        assert error is None

    @patch('src.versioning.resolvers.maven.robust_get')
    def test_unsatisfiable_range(self, mock_robust_get, resolver):
        """Test unsatisfiable range returns error."""
        mock_robust_get.return_value = (200, {}, """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <groupId>com.example</groupId>
  <artifactId>test</artifactId>
  <versioning>
    <versions>
      <version>1.0.0</version>
      <version>1.1.0</version>
      <version>2.0.0</version>
    </versions>
  </versioning>
</metadata>""")

        req = create_request("com.example:test", "[3.0,4.0)", ResolutionMode.RANGE)
        version, count, error = resolver.pick(req, ["1.0.0", "1.1.0", "2.0.0"])

        assert version is None
        assert count == 3
        assert "No versions match" in error

    @patch('src.versioning.resolvers.maven.robust_get')
    def test_fetch_candidates_caching(self, mock_robust_get, resolver, cache):
        """Test that fetch_candidates uses caching."""
        mock_xml = """<?xml version="1.0" encoding="UTF-8"?>
<metadata>
  <groupId>com.example</groupId>
  <artifactId>test</artifactId>
  <versioning>
    <versions>
      <version>1.0.0</version>
      <version>1.1.0</version>
      <version>2.0.0</version>
    </versions>
  </versioning>
</metadata>"""
        mock_robust_get.return_value = (200, {}, mock_xml)

        req = create_request("com.example:test")

        # First call should hit network
        candidates1 = resolver.fetch_candidates(req)
        assert mock_robust_get.call_count == 1
        assert candidates1 == ["1.0.0", "1.1.0", "2.0.0"]

        # Second call should use cache
        candidates2 = resolver.fetch_candidates(req)
        assert mock_robust_get.call_count == 1  # Still 1, used cache
        assert candidates2 == candidates1

    @patch('src.versioning.resolvers.maven.robust_get')
    def test_fetch_candidates_network_error(self, mock_robust_get, resolver):
        """Test fetch_candidates handles network errors gracefully."""
        mock_robust_get.return_value = (404, {}, "")

        req = create_request("com.example:nonexistent")
        candidates = resolver.fetch_candidates(req)

        assert candidates == []

    @patch('src.versioning.resolvers.maven.robust_get')
    def test_malformed_xml_handled(self, mock_robust_get, resolver):
        """Test handling of malformed XML."""
        mock_robust_get.return_value = (200, {}, "<invalid>xml<content>")

        req = create_request("com.example:test")
        candidates = resolver.fetch_candidates(req)

        assert candidates == []

    def test_invalid_group_artifact_format(self, resolver):
        """Test handling of invalid groupId:artifactId format."""
        req = create_request("invalid-format")
        candidates = resolver.fetch_candidates(req)

        assert candidates == []
