"""Version resolvers for different ecosystems."""

from .base import VersionResolver
from .npm import NpmVersionResolver
from .pypi import PyPIVersionResolver
from .maven import MavenVersionResolver
from .nuget import NuGetVersionResolver

__all__ = [
    "VersionResolver",
    "NpmVersionResolver",
    "PyPIVersionResolver",
    "MavenVersionResolver",
    "NuGetVersionResolver",
]
