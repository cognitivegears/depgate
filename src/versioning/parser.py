"""Token parsing utilities for package resolution."""

from typing import Optional, Tuple

from .models import Ecosystem, PackageRequest, ResolutionMode, VersionSpec


def tokenize_rightmost_colon(s: str) -> Tuple[str, Optional[str]]:
    """Return (identifier, spec or None) using the rightmost-colon rule.

    Does not assume ecosystem-specific syntax.
    """
    s = s.strip()
    if ':' not in s:
        return s, None
    parts = s.rsplit(':', 1)
    identifier = parts[0].strip()
    spec_part = parts[1].strip() if len(parts) > 1 else ''
    spec = spec_part if spec_part else None
    return identifier, spec


def _normalize_identifier(identifier: str, ecosystem: Ecosystem) -> str:
    """Apply ecosystem-specific identifier normalization."""
    if ecosystem == Ecosystem.PYPI:
        return identifier.lower().replace('_', '-')
    return identifier  # npm and maven preserve original


def _determine_resolution_mode(spec: str) -> ResolutionMode:
    """Determine resolution mode from spec string."""
    range_ops = ['^', '~', '*', 'x', '-', '<', '>', '=', '!', '~=', '[', ']', '(', ')', ',']
    if any(op in spec for op in range_ops):
        return ResolutionMode.RANGE
    return ResolutionMode.EXACT


def _determine_include_prerelease(spec: str, ecosystem: Ecosystem) -> bool:
    """Determine include_prerelease flag based on ecosystem and spec content."""
    if ecosystem == Ecosystem.NPM:
        return any(pre in spec.lower() for pre in ['pre', 'rc', 'alpha', 'beta'])
    return False  # pypi and maven default to False


def parse_cli_token(token: str, ecosystem: Ecosystem) -> PackageRequest:
    """Parse a CLI/list token into a PackageRequest.

    Uses rightmost-colon and ecosystem-aware normalization.
    """
    # Special handling for Maven coordinates that contain colons naturally
    if ecosystem == Ecosystem.MAVEN:
        colon_count = token.count(':')
        if colon_count <= 1:
            # Treat single-colon (groupId:artifactId) as identifier only, no version spec
            identifier = _normalize_identifier(token.strip(), ecosystem)
            requested_spec = None
            return PackageRequest(
                ecosystem=ecosystem,
                identifier=identifier,
                requested_spec=requested_spec,
                source="cli",
                raw_token=token
            )
        # For 2+ colons, split on rightmost to extract version spec
        id_part, spec = tokenize_rightmost_colon(token)
        identifier = _normalize_identifier(id_part, ecosystem)
    else:
        id_part, spec = tokenize_rightmost_colon(token)
        identifier = _normalize_identifier(id_part, ecosystem)

    if spec is None or (isinstance(spec, str) and spec.lower() == 'latest'):
        requested_spec = None
    else:
        mode = _determine_resolution_mode(spec)
        include_prerelease = _determine_include_prerelease(spec, ecosystem)
        requested_spec = VersionSpec(raw=spec, mode=mode, include_prerelease=include_prerelease)

    return PackageRequest(
        ecosystem=ecosystem,
        identifier=identifier,
        requested_spec=requested_spec,
        source="cli",
        raw_token=token
    )


def parse_manifest_entry(identifier: str, raw_spec: Optional[str], ecosystem: Ecosystem, source: str) -> PackageRequest:
    """Construct a PackageRequest from manifest fields.

    Preserves raw spec for logging while normalizing identifier and spec mode.
    """
    identifier = _normalize_identifier(identifier, ecosystem)

    if raw_spec is None or raw_spec.strip() == '' or raw_spec.lower() == 'latest':
        requested_spec = None
    else:
        spec = raw_spec.strip()
        mode = _determine_resolution_mode(spec)
        include_prerelease = _determine_include_prerelease(spec, ecosystem)
        requested_spec = VersionSpec(raw=spec, mode=mode, include_prerelease=include_prerelease)

    return PackageRequest(
        ecosystem=ecosystem,
        identifier=identifier,
        requested_spec=requested_spec,
        source=source,
        raw_token=None
    )
