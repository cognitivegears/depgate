"""Maven version resolver using Maven version range semantics."""

import re
import xml.etree.ElementTree as ET
from typing import List, Optional, Tuple

from packaging import version

# Support being imported as either "src.versioning.resolvers.maven" or "versioning.resolvers.maven"
try:
    from ...common.http_client import robust_get
    from ...constants import Constants
except Exception:  # ImportError or relative depth issues when imported as "versioning..."
    from common.http_client import robust_get
    from constants import Constants
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
        elif spec.mode == ResolutionMode.RANGE:
            return self._pick_range(spec.raw, candidates)
        else:
            return None, len(candidates), "Unsupported resolution mode"

    def _pick_latest(self, candidates: List[str]) -> Tuple[Optional[str], int, Optional[str]]:
        """Pick the highest stable (non-SNAPSHOT) version from candidates."""
        if not candidates:
            return None, 0, "No versions available"

        stable_versions = [v for v in candidates if not v.endswith("-SNAPSHOT")]

        if not stable_versions:
            # If no stable versions, pick highest SNAPSHOT
            try:
                parsed_versions = [version.Version(v) for v in candidates]
                parsed_versions.sort(reverse=True)
                return str(parsed_versions[0]), len(candidates), None
            except Exception as e:
                return None, len(candidates), f"Version parsing error: {str(e)}"

        try:
            # Parse and sort stable versions
            parsed_versions = []
            for v in stable_versions:
                try:
                    parsed_versions.append(version.Version(v))
                except Exception:
                    continue  # Skip invalid versions

            if not parsed_versions:
                return None, len(candidates), "No valid Maven versions found"

            # Sort and pick highest
            parsed_versions.sort(reverse=True)
            return str(parsed_versions[0]), len(candidates), None

        except Exception as e:
            return None, len(candidates), f"Version parsing error: {str(e)}"

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
            matching_versions.sort(key=lambda v: version.Version(v), reverse=True)
            return matching_versions[0], len(candidates), None

        except Exception as e:
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

    def _parse_bracket_range(self, range_spec: str, candidates: List[str]) -> List[str]:
        """Parse Maven bracket range notation like [1.0,2.0), (1.0,], or [1.2]."""
        # Remove outer bracket/paren characters
        inner = range_spec.strip()[1:-1] if len(range_spec) >= 2 else ""
        parts = inner.split(',') if ',' in inner else [inner]

        # Single-element bracket [1.2] means exact version (normalize minor-only to best match)
        if len(parts) == 1:
            base = parts[0].strip()
            if not base:
                return []
            # Match exact or prefix (e.g., "1.2" -> pick versions starting with "1.2.")
            matching = []
            for v in candidates:
                try:
                    ver = version.Version(v)
                    if v == base or ver.base_version == base or v.startswith(base + "."):
                        matching.append(v)
                except Exception:
                    continue
            return matching

        lower_str, upper_str = parts[0].strip(), parts[1].strip()
        lower_inclusive = range_spec.startswith('[')
        upper_inclusive = range_spec.endswith(']')

        matching = []
        for v in candidates:
            try:
                ver = version.Version(v)

                # Check lower bound
                if lower_str:
                    lower_ver = version.Version(lower_str)
                    if lower_inclusive and ver < lower_ver:
                        continue
                    if not lower_inclusive and ver <= lower_ver:
                        continue

                # Check upper bound
                if upper_str:
                    upper_ver = version.Version(upper_str)
                    if upper_inclusive and ver > upper_ver:
                        continue
                    if not upper_inclusive and ver >= upper_ver:
                        continue

                matching.append(v)

            except Exception:
                continue

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
