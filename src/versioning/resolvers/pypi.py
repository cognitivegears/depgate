"""PyPI version resolver using PEP 440 versioning."""

from typing import List, Optional, Tuple

from packaging import version
from packaging.version import InvalidVersion
from packaging.specifiers import SpecifierSet, InvalidSpecifier
from packaging.requirements import Requirement

# Support being imported as either "src.versioning.resolvers.pypi" or "versioning.resolvers.pypi"
try:
    from ...common.http_client import get_json
    from ...constants import Constants
except ImportError:
    from common.http_client import get_json
    from constants import Constants
from ..models import Ecosystem, PackageRequest, ResolutionMode
from .base import VersionResolver


def _sanitize_identifier(identifier: str) -> str:
    """Return the package name without any version specifiers or extras."""
    try:
        # Use packaging.Requirement to parse and extract the name safely
        return Requirement(identifier).name
    except Exception:
        # Fallback: split on common version specifier characters
        for sep in [">=", "<=", ">", "<", "==", "~=", "!=", "==="]:
            if sep in identifier:
                return identifier.split(sep)[0]
        # If no specifier found, return as‑is
        return identifier


class PyPIVersionResolver(VersionResolver):
    """Resolver for PyPI packages using PEP 440 versioning."""

    @property
    def ecosystem(self) -> Ecosystem:
        """Return PyPI ecosystem."""
        return Ecosystem.PYPI

    def fetch_candidates(self, req: PackageRequest) -> List[str]:
        """Fetch version candidates from PyPI Warehouse JSON API.

        Args:
            req: Package request

        Returns:
            List of version strings
        """
        cache_key = f"pypi:{req.identifier}"
        if self.cache:
            cached = self.cache.get(cache_key)
            if cached is not None:
                return cached

        # Ensure we strip any whitespace and version specifiers from the identifier
        sanitized_name = _sanitize_identifier(req.identifier).strip()
        url = f"{Constants.REGISTRY_URL_PYPI}{sanitized_name}/json"
        status_code, _, data = get_json(url)

        if status_code != 200 or not data:
            return []

        # Extract versions from releases, filter out yanked
        versions = []
        releases = data.get("releases", {})

        for ver_str, files in releases.items():
            # Check if any file is yanked
            is_yanked = any(file_info.get("yanked", False) for file_info in files)
            if not is_yanked:
                versions.append(ver_str)

        if self.cache:
            self.cache.set(cache_key, versions, 600)  # 10 minutes TTL

        return versions

    def pick(
        self, req: PackageRequest, candidates: List[str]
    ) -> Tuple[Optional[str], int, Optional[str]]:
        """Apply PEP 440 rules to select version.

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
        """Pick the highest version from candidates."""
        if not candidates:
            return None, 0, "No versions available"

        # Parse and sort versions using packaging
        parsed_versions = []
        for v in candidates:
            try:
                parsed_versions.append(version.Version(v))
            except InvalidVersion:
                continue  # Skip invalid versions

        if not parsed_versions:
            return None, len(candidates), "No valid PEP 440 versions found"

        # Sort and pick highest
        parsed_versions.sort(reverse=True)
        return str(parsed_versions[0]), len(candidates), None

    def _pick_exact(self, version_str: str, candidates: List[str]) -> Tuple[Optional[str], int, Optional[str]]:
        """Check if exact version exists in candidates."""
        if version_str in candidates:
            return version_str, len(candidates), None
        return None, len(candidates), f"Version {version_str} not found"

    def _pick_range(
        self, spec_str: str, candidates: List[str], include_prerelease: bool
    ) -> Tuple[Optional[str], int, Optional[str]]:
        """Apply PEP 440 specifier and pick highest matching version."""
        try:
            spec = SpecifierSet(spec_str)
        except InvalidSpecifier as e:
            return None, len(candidates), f"Invalid PEP 440 spec: {str(e)}"

        matching_versions = []
        for v in candidates:
            try:
                ver = version.Version(v)
                # Skip pre-releases unless explicitly allowed
                if ver.is_prerelease and not include_prerelease:
                    continue
                if ver in spec:
                    matching_versions.append(ver)
            except InvalidVersion:
                continue  # Skip invalid versions

        if not matching_versions:
            # Do not select pre-releases by default when no stable versions satisfy the range
            return None, len(candidates), f"No versions match spec '{spec_str}'"

        # Sort and pick highest
        matching_versions.sort(reverse=True)
        return str(matching_versions[0]), len(candidates), None
