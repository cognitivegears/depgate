"""DepGate proxy server package.

This package provides HTTP proxy functionality that intercepts package manager
requests (npm, pypi, maven, nuget), evaluates packages against policies, and
allows or blocks based on policy decisions.
"""

from .request_parser import RequestParser, ParsedRequest, RegistryType
from .cache import DecisionCache
from .upstream import UpstreamClient
from .evaluator import ProxyEvaluator
from .server import RegistryProxyServer, ProxyConfig

__all__ = [
    "RequestParser",
    "ParsedRequest",
    "RegistryType",
    "DecisionCache",
    "UpstreamClient",
    "ProxyEvaluator",
    "RegistryProxyServer",
    "ProxyConfig",
]
