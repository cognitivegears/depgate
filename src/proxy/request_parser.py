"""Request parser for extracting package information from registry URLs."""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class RegistryType(Enum):
    """Supported registry types."""

    NPM = "npm"
    PYPI = "pypi"
    MAVEN = "maven"
    NUGET = "nuget"
    UNKNOWN = "unknown"


@dataclass
class ParsedRequest:
    """Result of parsing a registry request."""

    registry_type: RegistryType
    package_name: str
    version: Optional[str] = None
    is_metadata_request: bool = True
    is_tarball_request: bool = False
    raw_path: str = ""


class RequestParser:
    """Parser for extracting package/version info from registry request URLs."""

    # NPM patterns
    # /{package} - package metadata
    # /{@scope/package} - scoped package metadata
    # /{package}/-/{package}-{version}.tgz - tarball
    # /{@scope/package}/-/{package}-{version}.tgz - scoped tarball
    _NPM_SCOPED_PATTERN = re.compile(r"^/@([^/]+)/([^/]+)(?:/(.*))?$")
    _NPM_UNSCOPED_PATTERN = re.compile(r"^/([^/@][^/]*)(?:/(.*))?$")
    _NPM_TARBALL_PATTERN = re.compile(
        r"^-/(.+)-(\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?(?:\+[a-zA-Z0-9.-]+)?)\.tgz$"
    )

    # PyPI patterns
    # /simple/{package}/ - simple API (PEP 503)
    # /pypi/{package}/json - JSON API
    # /pypi/{package}/{version}/json - JSON API for specific version
    # /packages/{...}/{package}-{version}.tar.gz - tarball
    _PYPI_SIMPLE_PATTERN = re.compile(r"^/simple/([^/]+)/?$")
    _PYPI_JSON_PATTERN = re.compile(r"^/pypi/([^/]+)(?:/([^/]+))?/json$")
    # sdist/zip: greedy name, version must start with a digit and contain
    # no hyphens (PEP 440 normalized versions never contain hyphens).
    _PYPI_SDIST_PATTERN = re.compile(
        r"^/packages/[^/]+/[^/]+/[^/]+/(.*)-(\d[^-]*)\.(?:tar\.gz|zip)$"
    )
    # wheel (PEP 427): {name}-{version}(-{build})?-{python}-{abi}-{platform}.whl
    # Normalized wheel names/versions never contain hyphens.
    _PYPI_WHEEL_PATTERN = re.compile(
        r"^/packages/[^/]+/[^/]+/[^/]+/([^-]+)-([^-]+)(?:-[^-]+){3,4}\.whl$"
    )

    # Maven patterns
    # /maven2/{group}/{artifact}/{version}/{artifact}-{version}.pom
    # /maven2/{group}/{artifact}/{version}/{artifact}-{version}.jar
    # /maven2/{group}/{artifact}/maven-metadata.xml
    # Note: group path can have multiple segments (org/apache/commons)
    # artifact is the second-to-last segment before maven-metadata.xml
    _MAVEN_ARTIFACT_PATTERN = re.compile(
        r"^/(?:maven2/)?(.+)/([^/]+)/([^/]+)/\2-\3(?:-[^.]+)?\.(pom|jar|war|aar)$"
    )
    # For metadata, we need to find the artifact (last segment before maven-metadata.xml)
    # and group (everything before that)
    _MAVEN_METADATA_PATTERN = re.compile(r"^/(?:maven2/)?((?:[^/]+/)*[^/]+)/([^/]+)/maven-metadata\.xml$")
    _MAVEN_VERSION_METADATA_PATTERN = re.compile(
        r"^/(?:maven2/)?((?:[^/]+/)*[^/]+)/([^/]+)/([^/]+)/maven-metadata\.xml$"
    )

    # NuGet patterns
    # /v3/registration5-gz-semver2/{package}/index.json - registration
    # /v3/registration5-gz-semver2/{package}/{version}.json - version registration
    # /v3-flatcontainer/{package}/index.json - flat container
    # /v3-flatcontainer/{package}/{version}/{package}.{version}.nupkg - package download
    _NUGET_REGISTRATION_PATTERN = re.compile(
        r"^/v3/registration\d*(?:-[^/]+)?/([^/]+)(?:/index\.json|/(\d+\.\d+\.\d+(?:[a-zA-Z0-9.-]*)?)\.json)?$"
    )
    _NUGET_FLATCONTAINER_PATTERN = re.compile(
        r"^/v3-flatcontainer/([^/]+)(?:/index\.json|/(\d+\.\d+\.\d+(?:[a-zA-Z0-9.-]*)?)/.*)?$"
    )

    def __init__(self, default_registry: RegistryType = RegistryType.NPM):
        """Initialize the request parser.

        Args:
            default_registry: Default registry type when auto-detection fails.
        """
        self._default_registry = default_registry

    def parse(self, path: str, registry_hint: Optional[RegistryType] = None) -> ParsedRequest:
        """Parse a request path to extract package information.

        Args:
            path: The URL path to parse.
            registry_hint: Optional hint for the registry type.

        Returns:
            ParsedRequest with extracted information.
        """
        # Normalize path
        path = urllib.parse.unquote(path)
        if not path.startswith("/"):
            path = "/" + path

        # Try registry-specific parsing based on hint
        if registry_hint:
            result = self._parse_for_registry(path, registry_hint)
            if result:
                return result
            return ParsedRequest(
                registry_type=registry_hint,
                package_name="",
                raw_path=path,
            )

        # Auto-detect registry type from URL patterns
        # Try more specific patterns first (PyPI, Maven, NuGet have distinctive paths)
        # NPM is most generic so try it last
        for registry_type in [RegistryType.PYPI, RegistryType.MAVEN, RegistryType.NUGET, RegistryType.NPM]:
            result = self._parse_for_registry(path, registry_type)
            if result and result.package_name:
                return result

        # No pattern matched; fall back to registry_hint or default registry
        return ParsedRequest(
            registry_type=registry_hint or self._default_registry,
            package_name="",
            raw_path=path,
        )

    def _parse_for_registry(self, path: str, registry_type: RegistryType) -> Optional[ParsedRequest]:
        """Parse path for a specific registry type."""
        if registry_type == RegistryType.NPM:
            return self._parse_npm(path)
        elif registry_type == RegistryType.PYPI:
            return self._parse_pypi(path)
        elif registry_type == RegistryType.MAVEN:
            return self._parse_maven(path)
        elif registry_type == RegistryType.NUGET:
            return self._parse_nuget(path)
        return None

    def _parse_npm(self, path: str) -> Optional[ParsedRequest]:
        """Parse NPM registry request."""
        # Try scoped package first
        match = self._NPM_SCOPED_PATTERN.match(path)
        if match:
            scope, name, rest = match.groups()
            package_name = f"@{scope}/{name}"

            if rest:
                # Check if it's a tarball request
                tarball_match = self._NPM_TARBALL_PATTERN.match(rest)
                if tarball_match:
                    _, version = tarball_match.groups()
                    return ParsedRequest(
                        registry_type=RegistryType.NPM,
                        package_name=package_name,
                        version=version,
                        is_metadata_request=False,
                        is_tarball_request=True,
                        raw_path=path,
                    )
                if rest.startswith("-/") and rest.endswith(".tgz"):
                    version = self._fallback_npm_tarball_version(rest)
                    if version:
                        return ParsedRequest(
                            registry_type=RegistryType.NPM,
                            package_name=package_name,
                            version=version,
                            is_metadata_request=False,
                            is_tarball_request=True,
                            raw_path=path,
                        )
                # Could be a version request like /{package}/{version}
                version = rest
                return ParsedRequest(
                    registry_type=RegistryType.NPM,
                    package_name=package_name,
                    version=version if version and not version.startswith("-") else None,
                    is_metadata_request=True,
                    raw_path=path,
                )

            return ParsedRequest(
                registry_type=RegistryType.NPM,
                package_name=package_name,
                is_metadata_request=True,
                raw_path=path,
            )

        # Try unscoped package
        match = self._NPM_UNSCOPED_PATTERN.match(path)
        if match:
            name, rest = match.groups()

            # Skip special paths
            if name in ("-", "_", "favicon.ico"):
                return None

            if rest:
                # Check if it's a tarball request
                tarball_match = self._NPM_TARBALL_PATTERN.match(rest)
                if tarball_match:
                    _, version = tarball_match.groups()
                    return ParsedRequest(
                        registry_type=RegistryType.NPM,
                        package_name=name,
                        version=version,
                        is_metadata_request=False,
                        is_tarball_request=True,
                        raw_path=path,
                    )
                if rest.startswith("-/") and rest.endswith(".tgz"):
                    version = self._fallback_npm_tarball_version(rest)
                    if version:
                        return ParsedRequest(
                            registry_type=RegistryType.NPM,
                            package_name=name,
                            version=version,
                            is_metadata_request=False,
                            is_tarball_request=True,
                            raw_path=path,
                        )
                # Could be a version request
                version = rest
                return ParsedRequest(
                    registry_type=RegistryType.NPM,
                    package_name=name,
                    version=version if version and not version.startswith("-") else None,
                    is_metadata_request=True,
                    raw_path=path,
                )

            return ParsedRequest(
                registry_type=RegistryType.NPM,
                package_name=name,
                is_metadata_request=True,
                raw_path=path,
            )

        return None

    def _fallback_npm_tarball_version(self, rest: str) -> Optional[str]:
        """Best-effort extraction of version from tarball filenames."""
        filename = rest[2:-4]  # strip "-/" and ".tgz"
        if "-" not in filename:
            return None
        _, version = filename.rsplit("-", 1)
        return version or None

    def _parse_pypi(self, path: str) -> Optional[ParsedRequest]:
        """Parse PyPI registry request."""
        # Try simple API
        match = self._PYPI_SIMPLE_PATTERN.match(path)
        if match:
            name = self._normalize_pypi_name(match.group(1))
            return ParsedRequest(
                registry_type=RegistryType.PYPI,
                package_name=name,
                is_metadata_request=True,
                raw_path=path,
            )

        # Try JSON API
        match = self._PYPI_JSON_PATTERN.match(path)
        if match:
            name = self._normalize_pypi_name(match.group(1))
            version = match.group(2)
            return ParsedRequest(
                registry_type=RegistryType.PYPI,
                package_name=name,
                version=version,
                is_metadata_request=True,
                raw_path=path,
            )

        # Try sdist/zip download
        match = self._PYPI_SDIST_PATTERN.match(path)
        if match:
            name = self._normalize_pypi_name(match.group(1))
            version = match.group(2)
            return ParsedRequest(
                registry_type=RegistryType.PYPI,
                package_name=name,
                version=version,
                is_metadata_request=False,
                is_tarball_request=True,
                raw_path=path,
            )

        # Try wheel download
        match = self._PYPI_WHEEL_PATTERN.match(path)
        if match:
            name = self._normalize_pypi_name(match.group(1))
            version = match.group(2)
            return ParsedRequest(
                registry_type=RegistryType.PYPI,
                package_name=name,
                version=version,
                is_metadata_request=False,
                is_tarball_request=True,
                raw_path=path,
            )

        return None

    def _normalize_pypi_name(self, name: str) -> str:
        """Normalize PyPI package name per PEP 503."""
        return re.sub(r"[-_.]+", "-", name.lower())

    def _parse_maven(self, path: str) -> Optional[ParsedRequest]:
        """Parse Maven registry request."""
        # Try artifact pattern first (most specific)
        match = self._MAVEN_ARTIFACT_PATTERN.match(path)
        if match:
            group_path, artifact, version, _ = match.groups()
            group_id = group_path.replace("/", ".")
            package_name = f"{group_id}:{artifact}"
            return ParsedRequest(
                registry_type=RegistryType.MAVEN,
                package_name=package_name,
                version=version,
                is_metadata_request=False,
                is_tarball_request=True,
                raw_path=path,
            )

        # Try version metadata pattern - only if the third-to-last segment looks like a version
        match = self._MAVEN_VERSION_METADATA_PATTERN.match(path)
        if match:
            group_path, artifact, potential_version = match.groups()
            # Check if it looks like a version (starts with digit or is a common version pattern)
            if potential_version and (
                potential_version[0].isdigit() or
                potential_version.startswith("v") or
                "-SNAPSHOT" in potential_version
            ):
                group_id = group_path.replace("/", ".")
                package_name = f"{group_id}:{artifact}"
                return ParsedRequest(
                    registry_type=RegistryType.MAVEN,
                    package_name=package_name,
                    version=potential_version,
                    is_metadata_request=True,
                    raw_path=path,
                )
            # Otherwise treat as metadata pattern (artifact is the potential_version)
            # Group is group_path + artifact
            full_group_path = f"{group_path}/{artifact}"
            group_id = full_group_path.replace("/", ".")
            package_name = f"{group_id}:{potential_version}"
            return ParsedRequest(
                registry_type=RegistryType.MAVEN,
                package_name=package_name,
                is_metadata_request=True,
                raw_path=path,
            )

        # Try metadata pattern (least specific)
        match = self._MAVEN_METADATA_PATTERN.match(path)
        if match:
            group_path, artifact = match.groups()
            group_id = group_path.replace("/", ".")
            package_name = f"{group_id}:{artifact}"
            return ParsedRequest(
                registry_type=RegistryType.MAVEN,
                package_name=package_name,
                is_metadata_request=True,
                raw_path=path,
            )

        return None

    def _parse_nuget(self, path: str) -> Optional[ParsedRequest]:
        """Parse NuGet registry request."""
        # Try registration pattern
        match = self._NUGET_REGISTRATION_PATTERN.match(path)
        if match:
            name = match.group(1).lower()
            version = match.group(2) if len(match.groups()) > 1 else None
            return ParsedRequest(
                registry_type=RegistryType.NUGET,
                package_name=name,
                version=version,
                is_metadata_request=True,
                raw_path=path,
            )

        # Try flat container pattern
        match = self._NUGET_FLATCONTAINER_PATTERN.match(path)
        if match:
            name = match.group(1).lower()
            version = match.group(2) if len(match.groups()) > 1 else None
            is_tarball = version is not None and path.endswith(".nupkg")
            return ParsedRequest(
                registry_type=RegistryType.NUGET,
                package_name=name,
                version=version,
                is_metadata_request=not is_tarball,
                is_tarball_request=is_tarball,
                raw_path=path,
            )

        return None
