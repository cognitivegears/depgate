"""Token parsing utilities for package resolution."""
import re

from typing import Optional, Tuple, List, Dict

from .models import (
    Ecosystem,
    PackageRequest,
    ResolutionMode,
    VersionSpec,
    DependencyRecord,
    RelationType,
    RequirementType,
    ScopeType,
)


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
    For PyPI, support colon-delimited CLI spec (e.g., 'name:1.2.3') for backward-compat,
    otherwise prefer PEP 508 parsing to strip extras/specifiers.
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
        if ecosystem == Ecosystem.PYPI:
            # Support colon-delimited CLI spec first (backward-compat with tests)
            if ":" in token:
                id_part, spec = tokenize_rightmost_colon(token)
            else:
                # Prefer robust PEP 508 parsing for PyPI tokens
                try:
                    from packaging.requirements import Requirement  # lazy import
                    r = Requirement(str(token))
                    id_part = r.name
                    spec = str(r.specifier) if str(r.specifier) else None
                except Exception:
                    # Fallback to heuristic splitter
                    name_part, pep_spec = _split_spec(str(token))
                    id_part, spec = name_part, pep_spec
            identifier = _normalize_identifier(id_part, ecosystem)
        else:
            # npm and others: only split rightmost colon (scoped npm names may include '/')
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


# -----------------------------
# PyPI manifest/lockfile helpers
# -----------------------------

def _split_spec(req: str) -> Tuple[str, Optional[str]]:
    """Best-effort split of a requirement string into (name, spec).

    Handles patterns like:
      - "package>=1.2.3"
      - "package[extra1,extra2]>=1.2; python_version>='3.10'"
      - "package" (no spec)
    """
    if not req:
        return "", None

    s = req.strip()
    # Drop environment markers
    s = s.split(";", 1)[0].strip()

    # Separate extras (PEP 508) from the base name section
    if "[" in s:
        name_base = s.split("[", 1)[0].strip()
    else:
        name_base = s

    # Find first comparator occurrence after the base name segment
    comparators = ["===", ">=", "<=", "==", "~=", "!=", ">", "<", " "]
    start = len(name_base)
    first_idx: Optional[int] = None
    for op in comparators:
        idx = s.find(op, start)
        if idx != -1:
            first_idx = idx if first_idx is None else min(first_idx, idx)
    spec: Optional[str] = None
    if first_idx is not None and first_idx >= start and first_idx < len(s):
        spec = s[first_idx:].strip()
        name_text = s[:first_idx].strip()
    else:
        name_text = name_base.strip()

    # PEP 503 normalization for name
    name = name_text.lower().replace("_", "-")
    return name, (spec if spec else None)


def parse_requirements_txt(manifest_path: str) -> Dict[str, DependencyRecord]:
    """Parse requirements.txt for direct dependencies (normal/required)."""
    results: Dict[str, DependencyRecord] = {}
    try:
        with open(manifest_path, 'r', encoding='utf-8') as fh:
            for line in fh:
                raw = line.strip()
                if not raw or raw.startswith('#') or raw.startswith('-r') or raw.startswith('--requirement'):
                    continue
                name, _spec = _split_spec(raw)
                if not name:
                    continue
                rec = results.get(name)
                if rec is None:
                    rec = DependencyRecord(
                        name=name,
                        ecosystem="pypi",
                        requested_spec=raw,
                        relation=RelationType.DIRECT,
                        requirement=RequirementType.REQUIRED,
                        scope=ScopeType.NORMAL,
                    )
                    rec.add_origin(manifest_path, "requirements.txt")
                    results[name] = rec
                else:
                    # Prefer stronger requirement/scope if encountered
                    rec.prefer_requirement(RequirementType.REQUIRED)
                    rec.prefer_scope(ScopeType.NORMAL)
        return results
    except Exception:
        return results


def parse_pyproject_tools(manifest_path: str) -> Dict[str, bool]:
    """Detect tool sections in pyproject.toml to guide precedence."""
    try:
        try:
            import tomllib as toml  # type: ignore
        except Exception:  # pylint: disable=broad-exception-caught
            import tomli as toml  # type: ignore
        with open(manifest_path, 'rb') as fh:
            data = toml.load(fh) or {}
        tool = data.get('tool', {}) or {}
        return {
            "tool_uv": bool(tool.get('uv')),
            "tool_poetry": bool(tool.get('poetry')),
        }
    except Exception:  # pylint: disable=broad-exception-caught
        return {"tool_uv": False, "tool_poetry": False}


def parse_pyproject_for_direct_pypi(manifest_path: str) -> Dict[str, DependencyRecord]:
    """Parse pyproject.toml for direct dependencies across PEP 621 and Poetry."""
    results: Dict[str, DependencyRecord] = {}
    try:
        try:
            import tomllib as toml  # type: ignore
        except Exception:  # pylint: disable=broad-exception-caught
            import tomli as toml  # type: ignore
        with open(manifest_path, 'rb') as fh:
            data = toml.load(fh) or {}

        # PEP 621
        proj = data.get('project', {}) or {}
        deps = proj.get('dependencies', []) or []
        for entry in deps:
            name, spec = _split_spec(str(entry))
            if not name:
                continue
            rec = results.get(name)
            if rec is None:
                rec = DependencyRecord(
                    name=name,
                    ecosystem="pypi",
                    requested_spec=spec if spec else str(entry),
                    relation=RelationType.DIRECT,
                    requirement=RequirementType.REQUIRED,
                    scope=ScopeType.NORMAL,
                )
                rec.add_origin(manifest_path, "project.dependencies")
                results[name] = rec
            else:
                rec.prefer_requirement(RequirementType.REQUIRED)
                rec.prefer_scope(ScopeType.NORMAL)

        opt_deps = proj.get('optional-dependencies', {}) or {}
        for group, entries in opt_deps.items():
            for entry in (entries or []):
                name, spec = _split_spec(str(entry))
                if not name:
                    continue
                rec = results.get(name)
                if rec is None:
                    rec = DependencyRecord(
                        name=name,
                        ecosystem="pypi",
                        requested_spec=spec if spec else str(entry),
                        relation=RelationType.DIRECT,
                        requirement=RequirementType.OPTIONAL,
                        scope=ScopeType.NORMAL,
                    )
                    rec.add_origin(manifest_path, f"project.optional-dependencies.{group}")
                    results[name] = rec
                else:
                    rec.prefer_scope(ScopeType.NORMAL)
                    # Optional only if not already required
                    rec.prefer_requirement(RequirementType.OPTIONAL)

        # Poetry (if present)
        tool = data.get('tool', {}) or {}
        poetry = tool.get('poetry', {}) or {}
        poetry_deps = poetry.get('dependencies', {}) or {}
        for k, v in poetry_deps.items():
            if k.lower() == "python":
                continue
            name = k.lower().replace('_', '-')
            requested = v if isinstance(v, str) else None
            rec = results.get(name)
            if rec is None:
                rec = DependencyRecord(
                    name=name,
                    ecosystem="pypi",
                    requested_spec=str(requested) if requested else None,
                    relation=RelationType.DIRECT,
                    requirement=RequirementType.REQUIRED,
                    scope=ScopeType.NORMAL,
                )
                rec.add_origin(manifest_path, "tool.poetry.dependencies")
                results[name] = rec
            else:
                rec.prefer_requirement(RequirementType.REQUIRED)
                rec.prefer_scope(ScopeType.NORMAL)

        poetry_group = poetry.get('group', {}) or {}
        # dev group
        dev = (poetry_group.get('dev', {}) or {}).get('dependencies', {}) or {}
        for k, v in dev.items():
            name = k.lower().replace('_', '-')
            requested = v if isinstance(v, str) else None
            rec = results.get(name)
            if rec is None:
                rec = DependencyRecord(
                    name=name,
                    ecosystem="pypi",
                    requested_spec=str(requested) if requested else None,
                    relation=RelationType.DIRECT,
                    requirement=RequirementType.REQUIRED,
                    scope=ScopeType.DEVELOPMENT,
                )
                rec.add_origin(manifest_path, "tool.poetry.group.dev.dependencies")
                results[name] = rec
            else:
                rec.prefer_requirement(RequirementType.REQUIRED)
                rec.prefer_scope(ScopeType.DEVELOPMENT)

        # any group named test
        test = (poetry_group.get('test', {}) or {}).get('dependencies', {}) or {}
        for k, v in test.items():
            name = k.lower().replace('_', '-')
            requested = v if isinstance(v, str) else None
            rec = results.get(name)
            if rec is None:
                rec = DependencyRecord(
                    name=name,
                    ecosystem="pypi",
                    requested_spec=str(requested) if requested else None,
                    relation=RelationType.DIRECT,
                    requirement=RequirementType.REQUIRED,
                    scope=ScopeType.TESTING,
                )
                rec.add_origin(manifest_path, "tool.poetry.group.test.dependencies")
                results[name] = rec
            else:
                rec.prefer_requirement(RequirementType.REQUIRED)
                rec.prefer_scope(ScopeType.TESTING)

        # Extras-only reachability => mark optional if not otherwise required
        extras = poetry.get('extras', {}) or {}
        for extra_name, pkgs in extras.items():
            for k in (pkgs or []):
                name = str(k).lower().replace('_', '-')
                rec = results.get(name)
                if rec is None:
                    rec = DependencyRecord(
                        name=name,
                        ecosystem="pypi",
                        requested_spec=None,
                        relation=RelationType.DIRECT,
                        requirement=RequirementType.OPTIONAL,
                        scope=ScopeType.NORMAL,
                    )
                    rec.add_origin(manifest_path, f"tool.poetry.extras.{extra_name}")
                    results[name] = rec
                else:
                    rec.prefer_requirement(RequirementType.OPTIONAL)
                    rec.prefer_scope(ScopeType.NORMAL)

        return results
    except Exception:
        return results
