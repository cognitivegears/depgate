"""Provider registry factory for creating provider clients.

Central factory that creates appropriate ProviderClient instances based on
ProviderType, with support for dependency injection for testing.
"""
from __future__ import annotations

from typing import Optional, Dict, Union

from .providers import ProviderType, ProviderClient
from .provider_adapters import GitHubProviderAdapter, GitLabProviderAdapter
from .github import GitHubClient
from .gitlab import GitLabClient


class ProviderRegistry:  # pylint: disable=too-few-public-methods
    """Factory for creating provider client instances.

    Supports dependency injection for testing by allowing pre-configured
    client instances to be passed in.
    """

    @staticmethod
    def get(
        ptype: ProviderType,
        injected: Optional[Dict[str, Union[GitHubClient, GitLabClient]]] = None,
    ) -> ProviderClient:
        """Get a provider client instance for the specified provider type.

        Args:
            ptype: The provider type to create a client for
            injected: Optional dict of pre-configured client instances for testing
                     Keys should be provider names ('github', 'gitlab')

        Returns:
            ProviderClient instance

        Raises:
            ValueError: If ptype is UNKNOWN (callers should check this first)
        """
        if ptype == ProviderType.UNKNOWN:
            raise ValueError("Cannot create client for unknown provider type")

        injected = injected or {}

        if ptype == ProviderType.GITHUB:
            github_client: GitHubClient
            if 'github' in injected:
                github_client = injected['github']  # type: ignore
            else:
                github_client = GitHubClient()
            return GitHubProviderAdapter(github_client)

        if ptype == ProviderType.GITLAB:
            gitlab_client: GitLabClient
            if 'gitlab' in injected:
                gitlab_client = injected['gitlab']  # type: ignore
            else:
                gitlab_client = GitLabClient()
            return GitLabProviderAdapter(gitlab_client)

        # This should never happen due to the UNKNOWN check above
        raise ValueError(f"Unsupported provider type: {ptype}")
