"""Data models for versioning and package resolution."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Tuple, List, Dict


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

# -------------------------------------------------------------------------
# Enums for enriched dependency metadata
# -------------------------------------------------------------------------

class RelationType(Enum):
    """Relation of a dependency to the root package."""
    DIRECT = "direct"
    TRANSITIVE = "transitive"


class RequirementType(Enum):
    """Whether a dependency is required or optional."""
    REQUIRED = "required"
    OPTIONAL = "optional"


class ScopeType(Enum):
    """Scope of a dependency within the ecosystem."""
    NORMAL = "normal"
    DEVELOPMENT = "development"
    TESTING = "testing"


# -------------------------------------------------------------------------
# Origin evidence dataclass
# -------------------------------------------------------------------------

@dataclass
class OriginEvidence:
    """Evidence of where a dependency was discovered."""
    file_path: str
    section: str


# -------------------------------------------------------------------------
# Dependency record dataclass (extended)
# -------------------------------------------------------------------------

@dataclass  # pylint: disable=too-many-instance-attributes
class DependencyRecord:
    """Enriched representation of a single dependency."""
    name: str
    ecosystem: str
    requested_spec: Optional[str] = None
    resolved_version: Optional[str] = None
    relation: Optional[RelationType] = None
    requirement: Optional[RequirementType] = None
    scope: Optional[ScopeType] = None
    source_files: List[OriginEvidence] = field(default_factory=list)
    lockfile: Optional[str] = None

    def add_origin(self, file_path: str, section: str) -> None:
        """Append a new origin evidence entry."""
        self.source_files.append(OriginEvidence(file_path=file_path, section=section))

    def prefer_requirement(self, new_req: RequirementType) -> None:
        """Prefer REQUIRED over OPTIONAL."""
        if self.requirement is None:
            self.requirement = new_req
        elif self.requirement == RequirementType.OPTIONAL and new_req == RequirementType.REQUIRED:
            self.requirement = new_req

    def prefer_scope(self, new_scope: ScopeType) -> None:
        """Prefer scopes with the following priority: NORMAL > DEVELOPMENT > TESTING."""
        priority = {
            ScopeType.NORMAL: 3,
            ScopeType.DEVELOPMENT: 2,
            ScopeType.TESTING: 1,
        }
        if self.scope is None:
            self.scope = new_scope
        else:
            if priority.get(new_scope, 0) > priority.get(self.scope, 0):
                self.scope = new_scope

    def mark_relation(self, rel: RelationType) -> None:
        """Set the relation type."""
        self.relation = rel


# -------------------------------------------------------------------------
# Resolution context dataclass
# -------------------------------------------------------------------------

@dataclass
class ResolutionContext:
    """Contextual information passed through the scanning/classification pipeline."""
    ecosystem: str
    manifest_path: Optional[str] = None
    lockfile_path: Optional[str] = None
    notes: Optional[Dict[str, str]] = None

# Duplicate metadata classes removed (previous duplication)
