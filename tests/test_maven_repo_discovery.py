import pytest

from metapackage import MetaPackage
from registry.maven import _enrich_with_repo

class DummyGitHubClient:
    def __init__(self):
        pass

    def get_repo(self, owner, repo):
        return {
            'stargazers_count': 123,
            'pushed_at': '2023-01-01T00:00:00Z'
        }

    def get_contributors_count(self, owner, repo):
        return 10

    def get_releases(self, owner, repo):
        # Provide a minimal releases list that the matcher can use
        return [{'name': '1.2.3', 'tag_name': '1.2.3'}]

class DummyGitLabClient:
    def __init__(self):
        pass

    def get_project(self, owner, repo):
        return {
            'star_count': 50,
            'last_activity_at': '2023-01-01T00:00:00Z'
        }

    def get_contributors_count(self, owner, repo):
        return 5

    def get_releases(self, owner, repo):
        return [{'name': '1.2.3', 'tag_name': '1.2.3'}]


@pytest.fixture(autouse=True)
def patch_provider_clients(monkeypatch):
    # Patch GitHub and GitLab clients used by src.registry.maven to avoid real network
    import registry.maven as maven_mod

    monkeypatch.setattr(maven_mod, 'GitHubClient', lambda: DummyGitHubClient())
    monkeypatch.setattr(maven_mod, 'GitLabClient', lambda: DummyGitLabClient())
    yield


def test_minimal_happy_path_with_scoped_asserts(monkeypatch):
    """
    Minimal smoke test to ensure the Maven enrichment runs without syntax errors
    and populates version match data when a repo is discovered.
    This intentionally keeps scope small to address earlier IndentationError.
    """
    # Patch internal helpers so we don't hit the network for metadata/POM
    import registry.maven as maven_mod

    # Resolve version immediately
    monkeypatch.setattr(maven_mod, '_resolve_latest_version', lambda g, a: '1.2.3')
    # POM fetch not needed as we'll simulate final normalized URL directly
    # Ensure _traverse_for_scm returns a normalized URL directly via fallback flow
    # We'll emulate that _normalize_scm_to_repo_url yielded a GitHub repo URL.
    def fake_traverse_for_scm(group, artifact, version, provenance, depth=0, max_depth=8):
        return {
            'scm': {'url': 'https://github.com/example/project'},
            'provenance': {'maven_pom.scm.url': 'https://github.com/example/project'}
        }
    monkeypatch.setattr(maven_mod, '_traverse_for_scm', fake_traverse_for_scm)

    mp = MetaPackage('org.apache.commons:commons-lang3')

    # Run enrichment; should populate repo fields and version match using dummy clients above
    _enrich_with_repo(mp, 'org.apache.commons', 'commons-lang3', '1.2.3')

    assert mp.repo_url_normalized == 'https://github.com/example/project'
    assert mp.repo_resolved is True
    assert mp.repo_exists is True
    assert mp.repo_version_match is not None
    assert mp.repo_version_match.get('matched') is True
