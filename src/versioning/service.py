"""Version resolution service coordinating multiple ecosystem resolvers."""

from typing import Dict, Sequence

from .cache import TTLCache
from .models import Ecosystem, PackageKey, PackageRequest, ResolutionMode, ResolutionResult
from .resolvers import MavenVersionResolver, NpmVersionResolver, PyPIVersionResolver


class VersionResolutionService:
    """Service for resolving package versions across multiple ecosystems."""

    def __init__(self, cache: TTLCache) -> None:
        """Initialize service with resolvers for each ecosystem.

        Args:
            cache: Shared TTL cache for metadata
        """
        self.resolvers = {
            Ecosystem.NPM: NpmVersionResolver(cache),
            Ecosystem.PYPI: PyPIVersionResolver(cache),
            Ecosystem.MAVEN: MavenVersionResolver(cache),
        }

    def resolve_all(self, requests: Sequence[PackageRequest]) -> Dict[PackageKey, ResolutionResult]:
        """Resolve versions for all package requests.

        Args:
            requests: Sequence of package resolution requests

        Returns:
            Dict mapping package keys to resolution results
        """
        results = {}

        for req in requests:
            key = (req.ecosystem, req.identifier)
            result = self._resolve_single(req)
            results[key] = result

        return results

    def _resolve_single(self, req: PackageRequest) -> ResolutionResult:
        """Resolve a single package request.

        Args:
            req: Package resolution request

        Returns:
            Resolution result
        """
        resolver = self.resolvers.get(req.ecosystem)
        if not resolver:
            return ResolutionResult(
                ecosystem=req.ecosystem,
                identifier=req.identifier,
                requested_spec=req.requested_spec.raw if req.requested_spec else None,
                resolved_version=None,
                resolution_mode=ResolutionMode.LATEST,
                candidate_count=0,
                error=f"Unsupported ecosystem: {req.ecosystem.value}"
            )

        # Fetch candidates
        candidates = resolver.fetch_candidates(req)

        # Determine resolution mode
        if not req.requested_spec:
            resolution_mode = ResolutionMode.LATEST
        else:
            resolution_mode = req.requested_spec.mode

        # Apply resolution logic
        resolved_version, candidate_count, error = resolver.pick(req, candidates)

        return ResolutionResult(
            ecosystem=req.ecosystem,
            identifier=req.identifier,
            requested_spec=req.requested_spec.raw if req.requested_spec else None,
            resolved_version=resolved_version,
            resolution_mode=resolution_mode,
            candidate_count=candidate_count,
            error=error
        )
