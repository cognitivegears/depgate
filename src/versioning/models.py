"""Data models for versioning and package resolution."""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Tuple


class Ecosystem(Enum):
    """Enum for supported ecosystems."""
    NPM = "npm"
    PYPI = "pypi"
    MAVEN = "maven"


class ResolutionMode(Enum):
    """Resolution strategy derived from the spec."""
    EXACT = "exact"
    RANGE = "range"
    LATEST = "latest"


@dataclass
class VersionSpec:
    """Normalized representation of a version spec and derived behavior flags."""
    raw: str
    mode: ResolutionMode
    include_prerelease: bool


@dataclass
class PackageRequest:
    """Resolution input across sources."""
    ecosystem: Ecosystem
    identifier: str  # normalized package name or Maven groupId:artifactId
    requested_spec: Optional[VersionSpec]
    source: str  # "cli" | "list" | "manifest" | "lockfile"
    raw_token: Optional[str]


@dataclass
class ResolutionResult:
    """Resolution outcome to feed downstream exports/logging."""
    ecosystem: Ecosystem
    identifier: str
    requested_spec: Optional[str]
    resolved_version: Optional[str]
    resolution_mode: ResolutionMode
    candidate_count: int
    error: Optional[str]


# Type alias for stable map key for lookups.
PackageKey = Tuple[Ecosystem, str]
