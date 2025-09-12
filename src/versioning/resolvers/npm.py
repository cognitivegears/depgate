"""NPM version resolver using semantic versioning."""

import re
import urllib.parse
from typing import List, Optional, Tuple

import semantic_version

# Support being imported as either "src.versioning.resolvers.npm" or "versioning.resolvers.npm"
try:
    # When imported via "src.versioning..."
    from ...common.http_client import get_json
    from ...constants import Constants
except ImportError:
    from common.http_client import get_json
    from constants import Constants
from ..models import Ecosystem, PackageRequest, ResolutionMode
from .base import VersionResolver


class NpmVersionResolver(VersionResolver):
    """Resolver for NPM packages using semantic versioning."""

    @property
    def ecosystem(self) -> Ecosystem:
        """Return NPM ecosystem."""
        return Ecosystem.NPM

    def fetch_candidates(self, req: PackageRequest) -> List[str]:
        """Fetch version candidates from NPM registry packument.

        Args:
            req: Package request

        Returns:
            List of version strings
        """
        cache_key = f"npm:{req.identifier}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        encoded = urllib.parse.quote(req.identifier, safe="")
        url = f"{Constants.REGISTRY_URL_NPM}{encoded}"
        status_code, _, data = get_json(url)

        if status_code != 200 or not data:
            return []

        versions = list(data.get("versions", {}).keys())
        if self.cache:
            self.cache.set(cache_key, versions, 600)  # 10 minutes TTL

        return versions

    def pick(
        self, req: PackageRequest, candidates: List[str]
    ) -> Tuple[Optional[str], int, Optional[str]]:
        """Apply NPM semver rules to select version.

        Args:
            req: Package request
            candidates: Available version strings

        Returns:
            Tuple of (resolved_version, candidate_count, error_message)
        """
        if not req.requested_spec:
            # Latest mode - pick highest version
            return self._pick_latest(candidates)

        spec = req.requested_spec
        if spec.mode == ResolutionMode.EXACT:
            return self._pick_exact(spec.raw, candidates)
        if spec.mode == ResolutionMode.RANGE:
            return self._pick_range(spec.raw, candidates, spec.include_prerelease)
        return None, len(candidates), "Unsupported resolution mode"

    def _pick_latest(self, candidates: List[str]) -> Tuple[Optional[str], int, Optional[str]]:
        """Pick the highest stable version from candidates (exclude prereleases)."""
        if not candidates:
            return None, 0, "No versions available"

        # Parse versions using semantic_version
        parsed_versions = []
        for v in candidates:
            try:
                parsed_versions.append(semantic_version.Version(v))
            except ValueError:
                continue  # Skip invalid versions

        if not parsed_versions:
            return None, len(candidates), "No valid semantic versions found"

        # Exclude prereleases by default for latest mode
        stable_versions = [ver for ver in parsed_versions if not ver.prerelease]
        if stable_versions:
            stable_versions.sort(reverse=True)
            return str(stable_versions[0]), len(candidates), None

        # No stable versions available
        return None, len(candidates), "No stable versions available"

    def _pick_exact(self, version: str, candidates: List[str]) -> Tuple[Optional[str], int, Optional[str]]:
        """Check if exact version exists in candidates."""
        if version in candidates:
            return version, len(candidates), None
        return None, len(candidates), f"Version {version} not found"

    def _normalize_spec(self, spec_str: str) -> str:
        """Normalize npm range syntax (hyphen, x-ranges) into SimpleSpec-compatible form."""
        s = spec_str.strip()

        # Hyphen ranges: "1.2.3 - 1.4.5" => ">=1.2.3, <=1.4.5"
        m = re.match(r'^\s*([0-9A-Za-z\.\-\+]+)\s*-\s*([0-9A-Za-z\.\-\+]+)\s*$', s)
        if m:
            left, right = m.group(1), m.group(2)
            # Use comma-separated comparators without spaces per SimpleSpec grammar
            return f">={left},<={right}"

        # x-ranges: 1.2.x or 1.x or 1.* -> convert to comparator pairs
        s2 = s.replace('*', 'x').lower()
        m = re.match(r'^\s*(\d+)\.(\d+)\.x\s*$', s2)
        if m:
            major, minor = int(m.group(1)), int(m.group(2))
            lower = f"{major}.{minor}.0"
            upper = f"{major}.{minor + 1}.0"
            return f">={lower},<{upper}"

        m = re.match(r'^\s*(\d+)\.x\s*$', s2)
        if m:
            major = int(m.group(1))
            lower = f"{major}.0.0"
            upper = f"{major + 1}.0.0"
            return f">={lower},<{upper}"

        # Plain major only (treated similarly to 1.x)
        m = re.match(r'^\s*(\d+)\s*$', s2)
        if m:
            major = int(m.group(1))
            lower = f"{major}.0.0"
            upper = f"{major + 1}.0.0"
            return f">={lower},<{upper}"

        return spec_str

    def _parse_semver_spec(self, spec_str: str):
        """Parse npm spec, fallback to normalized SimpleSpec. Returns (spec, error)."""
        try:
            return semantic_version.NpmSpec(spec_str), None
        except ValueError:
            try:
                norm = self._normalize_spec(spec_str)
                return semantic_version.SimpleSpec(norm), None
            except ValueError as e:
                return None, f"Invalid semver spec: {str(e)}"

    def _version_from_str(self, v: str) -> Optional[semantic_version.Version]:
        """Safely parse a semantic version string."""
        try:
            return semantic_version.Version(v)
        except ValueError:
            return None

    def _spec_matches(self, npm_spec, ver: semantic_version.Version) -> bool:
        """Check if a version matches an npm/simple spec, handling API differences."""
        is_match = getattr(npm_spec, "match", None)
        ok = False
        if callable(is_match):
            try:
                ok = bool(npm_spec.match(ver))
            except (TypeError, ValueError):
                try:
                    ok = bool(npm_spec.match(str(ver)))
                except (TypeError, ValueError):
                    ok = False
        else:
            try:
                ok = ver in npm_spec
            except TypeError:
                try:
                    ok = str(ver) in npm_spec  # type: ignore
                except (TypeError, ValueError, AttributeError):
                    ok = False
        return ok

    def _filter_matching_versions(
        self, candidates: List[str], npm_spec, include_prerelease: bool
    ) -> List[semantic_version.Version]:
        """Filter candidate strings to versions matching the given spec and prerelease flag."""
        matches: List[semantic_version.Version] = []
        for v in candidates:
            ver = self._version_from_str(v)
            if not ver:
                continue
            if ver.prerelease and not include_prerelease:
                continue
            if self._spec_matches(npm_spec, ver):
                matches.append(ver)
        return matches

    def _pick_range(
        self, spec_str: str, candidates: List[str], include_prerelease: bool
    ) -> Tuple[Optional[str], int, Optional[str]]:
        """Apply semver range and pick highest matching version."""
        npm_spec, err = self._parse_semver_spec(spec_str)
        if err or npm_spec is None:
            return None, len(candidates), err
        matching_versions = self._filter_matching_versions(candidates, npm_spec, include_prerelease)
        if not matching_versions:
            return None, len(candidates), f"No versions match spec '{spec_str}'"
        matching_versions.sort(reverse=True)
        return str(matching_versions[0]), len(candidates), None
