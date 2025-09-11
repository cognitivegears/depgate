"""Maven version resolver using Maven version range semantics."""

import xml.etree.ElementTree as ET
from typing import List, Optional, Tuple

from packaging import version
from packaging.version import InvalidVersion

# Support being imported as either "src.versioning.resolvers.maven" or "versioning.resolvers.maven"
try:
    from ...common.http_client import robust_get
except ImportError:
    from common.http_client import robust_get
from ..models import Ecosystem, PackageRequest, ResolutionMode
from .base import VersionResolver


class MavenVersionResolver(VersionResolver):
    """Resolver for Maven packages using Maven version range semantics."""

    @property
    def ecosystem(self) -> Ecosystem:
        """Return Maven ecosystem."""
        return Ecosystem.MAVEN

    def fetch_candidates(self, req: PackageRequest) -> List[str]:
        """Fetch version candidates from Maven metadata.xml.

        Args:
            req: Package request with identifier as "groupId:artifactId"

        Returns:
            List of version strings
        """
        cache_key = f"maven:{req.identifier}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        try:
            group_id, artifact_id = req.identifier.split(":", 1)
        except ValueError:
            return []

        # Construct Maven Central metadata URL
        url = f"https://repo1.maven.org/maven2/{group_id.replace('.', '/')}/{artifact_id}/maven-metadata.xml"
        status_code, _, text = robust_get(url)

        if status_code != 200 or not text:
            return []

        try:
            root = ET.fromstring(text)
            versions = []

            # Parse versioning/versions/version elements
            versioning = root.find("versioning")
            if versioning is not None:
                versions_elem = versioning.find("versions")
                if versions_elem is not None:
                    for version_elem in versions_elem.findall("version"):
                        ver_text = version_elem.text
                        if ver_text:
                            versions.append(ver_text.strip())

            if self.cache:
                self.cache.set(cache_key, versions, 600)  # 10 minutes TTL

            return versions

        except ET.ParseError:
            return []

    def pick(
        self, req: PackageRequest, candidates: List[str]
    ) -> Tuple[Optional[str], int, Optional[str]]:
        """Apply Maven version range rules to select version.

        Args:
            req: Package request
            candidates: Available version strings

        Returns:
            Tuple of (resolved_version, candidate_count, error_message)
        """
        if not req.requested_spec:
            # Latest mode - pick highest stable version
            return self._pick_latest(candidates)

        spec = req.requested_spec
        if spec.mode == ResolutionMode.EXACT:
            return self._pick_exact(spec.raw, candidates)
        if spec.mode == ResolutionMode.RANGE:
            return self._pick_range(spec.raw, candidates)
        return None, len(candidates), "Unsupported resolution mode"

    def _pick_latest(self, candidates: List[str]) -> Tuple[Optional[str], int, Optional[str]]:
        """Pick the highest stable (non-SNAPSHOT) version from candidates.

        Preserve the original Maven version string when returning, rather than
        the normalized PEP 440 string from packaging.Version. This avoids
        converting values like '6.0.0-RC2' into '6.0.0rc2', which can break
        downstream lookups (e.g., deps.dev expects Maven-style version text).
        """
        if not candidates:
            return None, 0, "No versions available"

        stable_versions = [v for v in candidates if not v.endswith("-SNAPSHOT")]

        if not stable_versions:
            # If no stable versions, pick highest SNAPSHOT, returning original string
            try:
                pairs = [(version.Version(v), v) for v in candidates]
                pairs.sort(key=lambda p: p[0], reverse=True)
                return pairs[0][1], len(candidates), None
            except InvalidVersion as e:
                return None, len(candidates), f"Version parsing error: {str(e)}"

        # Parse and sort stable versions with mapping back to original strings
        pairs: List[Tuple[version.Version, str]] = []
        for v in stable_versions:
            try:
                pairs.append((version.Version(v), v))
            except InvalidVersion:
                continue  # Skip invalid versions

        if not pairs:
            return None, len(candidates), "No valid Maven versions found"

        # Sort and pick highest, returning the original string form
        pairs.sort(key=lambda p: p[0], reverse=True)
        return pairs[0][1], len(candidates), None

    def _pick_exact(self, version_str: str, candidates: List[str]) -> Tuple[Optional[str], int, Optional[str]]:
        """Check if exact version exists in candidates."""
        if version_str in candidates:
            return version_str, len(candidates), None
        return None, len(candidates), f"Version {version_str} not found"

    def _pick_range(self, range_spec: str, candidates: List[str]) -> Tuple[Optional[str], int, Optional[str]]:
        """Apply Maven version range and pick highest matching version."""
        try:
            matching_versions = self._filter_by_range(range_spec, candidates)
            if not matching_versions:
                return None, len(candidates), f"No versions match range '{range_spec}'"

            # Sort and pick highest
            matching_versions.sort(key=version.Version, reverse=True)
            return matching_versions[0], len(candidates), None

        except (ValueError, InvalidVersion) as e:
            return None, len(candidates), f"Range parsing error: {str(e)}"

    def _filter_by_range(self, range_spec: str, candidates: List[str]) -> List[str]:
        """Filter candidates by Maven version range specification."""
        range_spec = range_spec.strip()

        # Handle bracket notation: [1.0,2.0), (1.0,], etc.
        if range_spec.startswith('[') or range_spec.startswith('('):
            return self._parse_bracket_range(range_spec, candidates)

        # Handle simple version (treated as exact)
        if not any(char in range_spec for char in '[()]'):
            return [range_spec] if range_spec in candidates else []

        # Handle comma-separated ranges
        if ',' in range_spec:
            return self._parse_comma_range(range_spec, candidates)

        return []

    def _match_single_bracket(self, base: str, candidates: List[str]) -> List[str]:
        """Match exact or prefix for single-element bracket [x] like [1.2]."""
        if not base:
            return []
        matching: List[str] = []
        for v in candidates:
            try:
                ver = version.Version(v)
                if v == base or ver.base_version == base or v.startswith(base + "."):
                    matching.append(v)
            except (InvalidVersion, ValueError, TypeError):
                continue
        return matching

    def _within_lower(self, ver: version.Version, lower_str: str, inclusive: bool) -> bool:
        """Check if version satisfies the lower bound."""
        if not lower_str:
            return True
        lower_ver = version.Version(lower_str)
        return ver >= lower_ver if inclusive else ver > lower_ver

    def _within_upper(self, ver: version.Version, upper_str: str, inclusive: bool) -> bool:
        """Check if version satisfies the upper bound."""
        if not upper_str:
            return True
        upper_ver = version.Version(upper_str)
        return ver <= upper_ver if inclusive else ver < upper_ver

    def _parse_bracket_range(self, range_spec: str, candidates: List[str]) -> List[str]:
        """Parse Maven bracket range notation like [1.0,2.0), (1.0,], or [1.2]."""
        inner = range_spec.strip()[1:-1] if len(range_spec) >= 2 else ""
        parts = inner.split(',') if ',' in inner else [inner]

        # Single-element bracket [1.2] means exact version (normalize minor-only to best match)
        if len(parts) == 1:
            return self._match_single_bracket(parts[0].strip(), candidates)

        lower_str, upper_str = parts[0].strip(), parts[1].strip()
        lower_inclusive = range_spec.startswith('[')
        upper_inclusive = range_spec.endswith(']')

        matching: List[str] = []
        for v in candidates:
            try:
                ver = version.Version(v)
            except (InvalidVersion, ValueError, TypeError):
                continue

            if not self._within_lower(ver, lower_str, lower_inclusive):
                continue
            if not self._within_upper(ver, upper_str, upper_inclusive):
                continue

            matching.append(v)

        return matching

    def _parse_comma_range(self, range_spec: str, candidates: List[str]) -> List[str]:
        """Parse comma-separated ranges like [1.0,2.0),[3.0,4.0]."""
        ranges = []
        current = ""
        paren_count = 0

        for char in range_spec:
            if char in '[(':
                if paren_count == 0:
                    if current:
                        ranges.append(current)
                    current = char
                else:
                    current += char
                paren_count += 1
            elif char in '])':
                paren_count -= 1
                current += char
                if paren_count == 0:
                    ranges.append(current)
                    current = ""
            else:
                current += char

        if current:
            ranges.append(current)

        # Union all matching versions from each range
        all_matching = set()
        for r in ranges:
            matching = self._parse_bracket_range(r, candidates)
            all_matching.update(matching)

        return list(all_matching)
