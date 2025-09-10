"""Tests for PyPI repository discovery functionality."""
import pytest
from unittest.mock import patch, MagicMock

from metapackage import MetaPackage
from registry.pypi import _extract_repo_candidates, _maybe_resolve_via_rtd, _enrich_with_repo


class TestExtractRepoCandidates:
    """Test _extract_repo_candidates function."""

    def test_extracts_repository_from_project_urls(self):
        """Test extraction of repository URLs from project_urls."""
        info = {
            'project_urls': {
                'Repository': 'https://github.com/owner/repo',
                'Homepage': 'https://example.com'
            },
            'home_page': 'https://fallback.com'
        }

        candidates = _extract_repo_candidates(info)

        assert candidates == ['https://github.com/owner/repo']

    def test_prioritizes_explicit_repo_keys(self):
        """Test that explicit repository keys are prioritized."""
        info = {
            'project_urls': {
                'Documentation': 'https://docs.example.com',
                'Repository': 'https://github.com/owner/repo',
                'Source': 'https://gitlab.com/owner/repo'
            },
            'home_page': 'https://fallback.com'
        }

        candidates = _extract_repo_candidates(info)

        # Should prioritize Repository and Source over Documentation
        assert 'https://github.com/owner/repo' in candidates
        assert 'https://gitlab.com/owner/repo' in candidates
        assert 'https://docs.example.com' in candidates

    def test_falls_back_to_home_page(self):
        """Test fallback to home_page when no repository URLs in project_urls."""
        info = {
            'project_urls': {
                'Documentation': 'https://docs.example.com'
            },
            'home_page': 'https://github.com/owner/repo'
        }

        candidates = _extract_repo_candidates(info)

        assert candidates == ['https://docs.example.com', 'https://github.com/owner/repo']

    def test_handles_missing_fields(self):
        """Test handling of missing project_urls or home_page."""
        info = {}

        candidates = _extract_repo_candidates(info)

        assert candidates == []


class TestMaybeResolveViaRtd:
    """Test _maybe_resolve_via_rtd function."""

    @patch('registry.pypi.resolve_repo_from_rtd')
    @patch('registry.pypi.infer_rtd_slug')
    def test_resolves_rtd_url(self, mock_infer, mock_resolve):
        """Test RTD URL resolution."""
        mock_infer.return_value = 'testproject'
        mock_resolve.return_value = 'https://github.com/owner/repo'

        result = _maybe_resolve_via_rtd('https://testproject.readthedocs.io/')

        assert result == 'https://github.com/owner/repo'
        mock_infer.assert_called_once_with('https://testproject.readthedocs.io/')
        mock_resolve.assert_called_once_with('https://testproject.readthedocs.io/')

    @patch('registry.pypi.resolve_repo_from_rtd')
    @patch('registry.pypi.infer_rtd_slug')
    def test_returns_none_for_non_rtd_url(self, mock_infer, mock_resolve):
        """Test that non-RTD URLs return None."""
        mock_infer.return_value = None

        result = _maybe_resolve_via_rtd('https://github.com/owner/repo')

        assert result is None
        mock_infer.assert_called_once_with('https://github.com/owner/repo')
        mock_resolve.assert_not_called()


class TestEnrichWithRepo:
    """Test _enrich_with_repo function."""

    @patch('registry.pypi.normalize_repo_url')
    @patch('registry.pypi.GitHubClient')
    def test_enriches_github_repo(self, mock_github_client, mock_normalize):
        """Test enrichment with GitHub repository."""
        # Setup mocks
        mock_repo_ref = MagicMock()
        mock_repo_ref.normalized_url = 'https://github.com/pandas-dev/pandas'
        mock_repo_ref.host = 'github'
        mock_repo_ref.owner = 'pandas-dev'
        mock_repo_ref.repo = 'pandas'
        mock_normalize.return_value = mock_repo_ref

        mock_client = MagicMock()
        mock_client.get_repo.return_value = {
            'stargazers_count': 35000,
            'pushed_at': '2023-01-01T00:00:00Z'
        }
        mock_client.get_contributors_count.return_value = 1500
        mock_client.get_releases.return_value = [
            {'name': 'v1.5.0', 'tag_name': 'v1.5.0'},
            {'name': 'v1.4.0', 'tag_name': 'v1.4.0'}
        ]
        mock_github_client.return_value = mock_client

        with patch('registry.pypi.VersionMatcher') as mock_matcher_class:
            mock_matcher = MagicMock()
            mock_matcher.find_match.return_value = {
                'matched': True,
                'match_type': 'v-prefix',
                'artifact': {'name': 'v1.5.0'},
                'tag_or_release': 'v1.5.0'
            }
            mock_matcher_class.return_value = mock_matcher

            # Create MetaPackage
            mp = MetaPackage('pandas')
            info = {
                'project_urls': {'Repository': 'https://github.com/pandas-dev/pandas'},
                'home_page': 'https://pandas.pydata.org'
            }

            # Call function
            _enrich_with_repo(mp, 'pandas', info, '1.5.0')

            # Assertions
            assert mp.repo_present_in_registry is True
            assert mp.repo_resolved is True
            assert mp.repo_url_normalized == 'https://github.com/pandas-dev/pandas'
            assert mp.repo_host == 'github'
            assert mp.repo_exists is True
            assert mp.repo_stars == 35000
            assert mp.repo_contributors == 1500
            assert mp.repo_last_activity_at == '2023-01-01T00:00:00Z'
            assert mp.repo_version_match == {
                'matched': True,
                'match_type': 'v-prefix',
                'artifact': {'name': 'v1.5.0'},
                'tag_or_release': 'v1.5.0'
            }
            assert mp.provenance == {'pypi_project_urls': 'https://github.com/pandas-dev/pandas'}

    @patch('registry.pypi.normalize_repo_url')
    @patch('registry.pypi._maybe_resolve_via_rtd')
    def test_enriches_rtd_fallback(self, mock_rtd_resolve, mock_normalize):
        """Test enrichment with RTD fallback."""
        # Setup mocks
        mock_rtd_resolve.return_value = 'https://github.com/owner/repo'

        mock_repo_ref = MagicMock()
        mock_repo_ref.normalized_url = 'https://github.com/owner/repo'
        mock_repo_ref.host = 'github'
        mock_repo_ref.owner = 'owner'
        mock_repo_ref.repo = 'repo'
        mock_normalize.return_value = mock_repo_ref

        # Create MetaPackage
        mp = MetaPackage('testpackage')
        info = {
            'project_urls': {'Documentation': 'https://testpackage.readthedocs.io/'},
            'home_page': 'https://example.com'
        }

        # Call function
        _enrich_with_repo(mp, 'testpackage', info, '1.0.0')

        # Assertions
        assert mp.repo_present_in_registry is True
        mock_rtd_resolve.assert_called_once_with('https://testpackage.readthedocs.io/')

    def test_handles_no_repo_found(self):
        """Test handling when no repository is found."""
        mp = MetaPackage('testpackage')
        info = {
            'project_urls': {'Homepage': 'https://example.com'},
            'home_page': 'https://example.com'
        }

        _enrich_with_repo(mp, 'testpackage', info, '1.0.0')

        assert mp.repo_present_in_registry is True  # homepage present
        assert mp.repo_resolved is False
        assert mp.repo_exists is None

    @patch('registry.pypi.normalize_repo_url')
    @patch('registry.pypi.GitHubClient')
    def test_handles_errors_gracefully(self, mock_github_client, mock_normalize):
        """Test that errors are handled gracefully."""
        # Setup mocks to raise exception
        mock_normalize.return_value = None  # Invalid URL

        mp = MetaPackage('testpackage')
        info = {
            'project_urls': {'Repository': 'invalid-url'},
            'home_page': 'https://example.com'
        }

        # Should not raise exception
        _enrich_with_repo(mp, 'testpackage', info, '1.0.0')

        assert mp.repo_present_in_registry is True
        assert mp.repo_present_in_registry is True
        assert mp.repo_resolved is False

    @patch('registry.pypi.normalize_repo_url')
    @patch('registry.pypi.GitHubClient')
    def test_enrich_with_repo_exact_mode_unsatisfiable_version(self, mock_github_client, mock_normalize):
        """Test enrichment guard for exact mode with unsatisfiable version."""
        # Setup mocks
        mock_repo_ref = MagicMock()
        mock_repo_ref.normalized_url = 'https://github.com/owner/repo'
        mock_repo_ref.host = 'github'
        mock_repo_ref.owner = 'owner'
        mock_repo_ref.repo = 'repo'
        mock_normalize.return_value = mock_repo_ref

        mock_client = MagicMock()
        mock_client.get_repo.return_value = {
            'stargazers_count': 1000,
            'pushed_at': '2023-01-01T00:00:00Z'
        }
        mock_client.get_contributors_count.return_value = 50
        mock_client.get_releases.return_value = [
            {'name': 'v1.0.0', 'tag_name': 'v1.0.0'}
        ]
        mock_client.get_tags.return_value = [
            {'name': 'v1.0.0', 'tag_name': 'v1.0.0'}
        ]
        mock_github_client.return_value = mock_client

        with patch('registry.pypi.VersionMatcher') as mock_matcher_class:
            mock_matcher = MagicMock()
            # Matcher should receive empty string when version is unsatisfiable
            mock_matcher.find_match.return_value = {
                'matched': False,
                'match_type': None,
                'artifact': None,
                'tag_or_release': None
            }
            mock_matcher_class.return_value = mock_matcher

            # Create MetaPackage with exact mode and no resolved version
            mp = MetaPackage('testpackage')
            mp.resolution_mode = 'exact'
            mp.resolved_version = None  # Version not resolved

            info = {
                'project_urls': {'Repository': 'https://github.com/owner/repo'},
                'home_page': 'https://example.com'
            }

            # Call function
            _enrich_with_repo(mp, 'testpackage', info, '1.0.0')

            # Assertions
            assert mp.repo_present_in_registry is True
            assert mp.repo_resolved is True
            assert mp.repo_exists is True
            assert mp.repo_stars == 1000
            assert mp.repo_version_match == {
                'matched': False,
                'match_type': None,
                'artifact': None,
                'tag_or_release': None
            }

            # Verify that matcher was called with empty string (not None)
            mock_matcher.find_match.assert_called_once_with('', mock_client.get_releases.return_value)
        assert mp.repo_resolved is False
