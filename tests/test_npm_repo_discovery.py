"""Tests for NPM repository discovery functionality."""
import pytest
from unittest.mock import patch, MagicMock

from metapackage import MetaPackage
from registry.npm import (
    _extract_latest_version,
    _parse_repository_field,
    _extract_fallback_urls,
    _enrich_with_repo
)


class TestExtractLatestVersion:
    """Test _extract_latest_version function."""

    def test_extracts_latest_from_dist_tags(self):
        """Test extraction of latest version from dist-tags."""
        packument = {
            'dist-tags': {
                'latest': '1.5.0',
                'beta': '2.0.0-beta'
            }
        }

        result = _extract_latest_version(packument)

        assert result == '1.5.0'

    def test_returns_empty_string_when_no_dist_tags(self):
        """Test handling when dist-tags is missing."""
        packument = {}

        result = _extract_latest_version(packument)

        assert result == ''

    def test_returns_empty_string_when_latest_missing(self):
        """Test handling when latest tag is missing."""
        packument = {
            'dist-tags': {
                'beta': '2.0.0-beta'
            }
        }

        result = _extract_latest_version(packument)

        assert result == ''


class TestParseRepositoryField:
    """Test _parse_repository_field function."""

    def test_parses_string_repository(self):
        """Test parsing string repository field."""
        version_info = {
            'repository': 'git+https://github.com/owner/repo.git'
        }

        url, directory = _parse_repository_field(version_info)

        assert url == 'git+https://github.com/owner/repo.git'
        assert directory is None

    def test_parses_object_repository_with_directory(self):
        """Test parsing object repository field with directory."""
        version_info = {
            'repository': {
                'type': 'git',
                'url': 'git+ssh://git@github.com:owner/repo.git',
                'directory': 'packages/foo'
            }
        }

        url, directory = _parse_repository_field(version_info)

        assert url == 'git+ssh://git@github.com:owner/repo.git'
        assert directory == 'packages/foo'

    def test_parses_object_repository_without_directory(self):
        """Test parsing object repository field without directory."""
        version_info = {
            'repository': {
                'type': 'git',
                'url': 'https://github.com/owner/repo.git'
            }
        }

        url, directory = _parse_repository_field(version_info)

        assert url == 'https://github.com/owner/repo.git'
        assert directory is None

    def test_returns_none_when_no_repository(self):
        """Test handling when repository field is missing."""
        version_info = {}

        url, directory = _parse_repository_field(version_info)

        assert url is None
        assert directory is None

    def test_returns_none_for_invalid_repository_type(self):
        """Test handling of invalid repository field type."""
        version_info = {
            'repository': 123  # Invalid type
        }

        url, directory = _parse_repository_field(version_info)

        assert url is None
        assert directory is None


class TestExtractFallbackUrls:
    """Test _extract_fallback_urls function."""

    def test_extracts_homepage_fallback(self):
        """Test extraction of homepage fallback."""
        version_info = {
            'homepage': 'https://github.com/owner/repo'
        }

        candidates = _extract_fallback_urls(version_info)

        assert candidates == ['https://github.com/owner/repo']

    def test_extracts_bugs_url_fallback(self):
        """Test extraction of bugs URL fallback."""
        version_info = {
            'bugs': {
                'url': 'https://github.com/owner/repo/issues'
            }
        }

        candidates = _extract_fallback_urls(version_info)

        assert candidates == ['https://github.com/owner/repo']

    def test_extracts_string_bugs_url_fallback(self):
        """Test extraction of string bugs URL fallback."""
        version_info = {
            'bugs': 'https://github.com/owner/repo/issues'
        }

        candidates = _extract_fallback_urls(version_info)

        assert candidates == ['https://github.com/owner/repo']

    def test_ignores_non_issues_bugs_url(self):
        """Test that non-issues bugs URLs are ignored."""
        version_info = {
            'bugs': 'https://github.com/owner/repo/blob/main/README.md'
        }

        candidates = _extract_fallback_urls(version_info)

        assert candidates == []

    def test_extracts_multiple_fallbacks(self):
        """Test extraction of multiple fallback URLs."""
        version_info = {
            'homepage': 'https://gitlab.com/group/repo',
            'bugs': 'https://github.com/owner/repo/issues'
        }

        candidates = _extract_fallback_urls(version_info)

        assert 'https://gitlab.com/group/repo' in candidates
        assert 'https://github.com/owner/repo' in candidates

    def test_returns_empty_list_when_no_fallbacks(self):
        """Test handling when no fallback URLs are available."""
        version_info = {}

        candidates = _extract_fallback_urls(version_info)

        assert candidates == []


class TestEnrichWithRepo:
    """Test _enrich_with_repo function."""

    @patch('registry.npm.normalize_repo_url')
    @patch('registry.npm.GitHubClient')
    def test_enriches_github_repo_from_repository_string(self, mock_github_client, mock_normalize):
        """Test enrichment with GitHub repository from string repository field."""
        # Setup mocks
        mock_repo_ref = MagicMock()
        mock_repo_ref.normalized_url = 'https://github.com/lodash/lodash'
        mock_repo_ref.host = 'github'
        mock_repo_ref.owner = 'lodash'
        mock_repo_ref.repo = 'lodash'
        mock_normalize.return_value = mock_repo_ref

        mock_client = MagicMock()
        mock_client.get_repo.return_value = {
            'stargazers_count': 50000,
            'pushed_at': '2023-01-01T00:00:00Z'
        }
        mock_client.get_contributors_count.return_value = 300
        mock_client.get_releases.return_value = [
            {'name': '4.17.21', 'tag_name': '4.17.21'},
            {'name': '4.17.20', 'tag_name': '4.17.20'}
        ]
        mock_github_client.return_value = mock_client

        with patch('registry.npm.VersionMatcher') as mock_matcher_class:
            mock_matcher = MagicMock()
            mock_matcher.find_match.return_value = {
                'matched': True,
                'match_type': 'exact',
                'artifact': {'name': '4.17.21'},
                'tag_or_release': '4.17.21'
            }
            mock_matcher_class.return_value = mock_matcher

            # Create MetaPackage and packument
            mp = MetaPackage('lodash')
            packument = {
                'dist-tags': {'latest': '4.17.21'},
                'versions': {
                    '4.17.21': {
                        'repository': 'git+https://github.com/lodash/lodash.git'
                    }
                }
            }

            # Call function
            _enrich_with_repo(mp, packument)

            # Assertions
            assert mp.repo_present_in_registry is True
            assert mp.repo_resolved is True
            assert mp.repo_url_normalized == 'https://github.com/lodash/lodash'
            assert mp.repo_host == 'github'
            assert mp.repo_exists is True
            assert mp.repo_stars == 50000
            assert mp.repo_contributors == 300
            assert mp.repo_last_activity_at == '2023-01-01T00:00:00Z'
            assert mp.repo_version_match == {
                'matched': True,
                'match_type': 'exact',
                'artifact': {'name': '4.17.21'},
                'tag_or_release': '4.17.21'
            }
            assert mp.provenance == {'npm_repository_field': 'git+https://github.com/lodash/lodash.git'}

    @patch('registry.npm.normalize_repo_url')
    @patch('registry.npm.GitHubClient')
    def test_enriches_github_repo_with_monorepo_directory(self, mock_github_client, mock_normalize):
        """Test enrichment with GitHub repository from object repository field with directory."""
        # Setup mocks
        mock_repo_ref = MagicMock()
        mock_repo_ref.normalized_url = 'https://github.com/babel/babel'
        mock_repo_ref.host = 'github'
        mock_repo_ref.owner = 'babel'
        mock_repo_ref.repo = 'babel'
        mock_normalize.return_value = mock_repo_ref

        mock_client = MagicMock()
        mock_client.get_repo.return_value = {
            'stargazers_count': 42000,
            'pushed_at': '2023-02-01T00:00:00Z'
        }
        mock_client.get_contributors_count.return_value = 800
        mock_client.get_releases.return_value = [
            {'name': '7.20.0', 'tag_name': '7.20.0'}
        ]
        mock_github_client.return_value = mock_client

        with patch('registry.npm.VersionMatcher') as mock_matcher_class:
            mock_matcher = MagicMock()
            mock_matcher.find_match.return_value = {
                'matched': True,
                'match_type': 'exact',
                'artifact': {'name': '7.20.0'},
                'tag_or_release': '7.20.0'
            }
            mock_matcher_class.return_value = mock_matcher

            # Create MetaPackage and packument
            mp = MetaPackage('babel-core')
            packument = {
                'dist-tags': {'latest': '7.20.0'},
                'versions': {
                    '7.20.0': {
                        'repository': {
                            'type': 'git',
                            'url': 'git+ssh://git@github.com:babel/babel.git',
                            'directory': 'packages/babel-core'
                        }
                    }
                }
            }

            # Call function
            _enrich_with_repo(mp, packument)

            # Assertions
            assert mp.repo_present_in_registry is True
            assert mp.repo_resolved is True
            assert mp.repo_url_normalized == 'https://github.com/babel/babel'
            assert mp.repo_host == 'github'
            assert mp.repo_exists is True
            assert mp.repo_stars == 42000
            assert mp.repo_contributors == 800
            assert mp.repo_last_activity_at == '2023-02-01T00:00:00Z'
            assert mp.repo_version_match == {
                'matched': True,
                'match_type': 'exact',
                'artifact': {'name': '7.20.0'},
                'tag_or_release': '7.20.0'
            }
            expected_provenance = {
                'npm_repository_field': 'git+ssh://git@github.com:babel/babel.git',
                'npm_repository_directory': 'packages/babel-core'
            }
            assert mp.provenance == expected_provenance

    @patch('registry.npm.normalize_repo_url')
    @patch('registry.npm.GitLabClient')
    def test_enriches_gitlab_repo_from_homepage_fallback(self, mock_gitlab_client, mock_normalize):
        """Test enrichment with GitLab repository from homepage fallback."""
        # Setup mocks
        mock_repo_ref = MagicMock()
        mock_repo_ref.normalized_url = 'https://gitlab.com/inkscape/inkscape'
        mock_repo_ref.host = 'gitlab'
        mock_repo_ref.owner = 'inkscape'
        mock_repo_ref.repo = 'inkscape'
        mock_normalize.return_value = mock_repo_ref

        mock_client = MagicMock()
        mock_client.get_project.return_value = {
            'star_count': 1200,
            'last_activity_at': '2023-03-01T00:00:00Z'
        }
        mock_client.get_contributors_count.return_value = 150
        mock_client.get_releases.return_value = [
            {'name': '1.2.0', 'tag_name': '1.2.0'}
        ]
        mock_gitlab_client.return_value = mock_client

        with patch('registry.npm.VersionMatcher') as mock_matcher_class:
            mock_matcher = MagicMock()
            mock_matcher.find_match.return_value = {
                'matched': True,
                'match_type': 'exact',
                'artifact': {'name': '1.2.0'},
                'tag_or_release': '1.2.0'
            }
            mock_matcher_class.return_value = mock_matcher

            # Create MetaPackage and packument
            mp = MetaPackage('inkscape')
            packument = {
                'dist-tags': {'latest': '1.2.0'},
                'versions': {
                    '1.2.0': {
                        'homepage': 'https://gitlab.com/inkscape/inkscape'
                    }
                }
            }

            # Call function
            _enrich_with_repo(mp, packument)

            # Assertions
            assert mp.repo_present_in_registry is True
            assert mp.repo_resolved is True
            assert mp.repo_url_normalized == 'https://gitlab.com/inkscape/inkscape'
            assert mp.repo_host == 'gitlab'
            assert mp.repo_exists is True
            assert mp.repo_stars == 1200
            assert mp.repo_contributors == 150
            assert mp.repo_last_activity_at == '2023-03-01T00:00:00Z'
            assert mp.repo_version_match == {
                'matched': True,
                'match_type': 'exact',
                'artifact': {'name': '1.2.0'},
                'tag_or_release': '1.2.0'
            }
            assert mp.provenance == {'npm_homepage': 'https://gitlab.com/inkscape/inkscape'}

    @patch('registry.npm.normalize_repo_url')
    @patch('registry.npm.GitHubClient')
    def test_enriches_github_repo_from_bugs_url_fallback(self, mock_github_client, mock_normalize):
        """Test enrichment with GitHub repository from bugs URL fallback."""
        # Setup mocks
        mock_repo_ref = MagicMock()
        mock_repo_ref.normalized_url = 'https://github.com/expressjs/express'
        mock_repo_ref.host = 'github'
        mock_repo_ref.owner = 'expressjs'
        mock_repo_ref.repo = 'express'
        mock_normalize.return_value = mock_repo_ref

        mock_client = MagicMock()
        mock_client.get_repo.return_value = {
            'stargazers_count': 60000,
            'pushed_at': '2023-04-01T00:00:00Z'
        }
        mock_client.get_contributors_count.return_value = 400
        mock_client.get_releases.return_value = [
            {'name': '4.18.2', 'tag_name': '4.18.2'}
        ]
        mock_github_client.return_value = mock_client

        with patch('registry.npm.VersionMatcher') as mock_matcher_class:
            mock_matcher = MagicMock()
            mock_matcher.find_match.return_value = {
                'matched': True,
                'match_type': 'exact',
                'artifact': {'name': '4.18.2'},
                'tag_or_release': '4.18.2'
            }
            mock_matcher_class.return_value = mock_matcher

            # Create MetaPackage and packument
            mp = MetaPackage('express')
            packument = {
                'dist-tags': {'latest': '4.18.2'},
                'versions': {
                    '4.18.2': {
                        'bugs': 'https://github.com/expressjs/express/issues'
                    }
                }
            }

            # Call function
            _enrich_with_repo(mp, packument)

            # Assertions
            assert mp.repo_present_in_registry is True
            assert mp.repo_resolved is True
            assert mp.repo_url_normalized == 'https://github.com/expressjs/express'
            assert mp.repo_host == 'github'
            assert mp.repo_exists is True
            assert mp.repo_stars == 60000
            assert mp.repo_contributors == 400
            assert mp.repo_last_activity_at == '2023-04-01T00:00:00Z'
            assert mp.repo_version_match == {
                'matched': True,
                'match_type': 'exact',
                'artifact': {'name': '4.18.2'},
                'tag_or_release': '4.18.2'
            }
            assert mp.provenance == {'npm_bugs_url': 'https://github.com/expressjs/express/issues'}

    def test_handles_no_repo_found(self):
        """Test handling when no repository is resolvable."""
        mp = MetaPackage('testpackage')
        packument = {
            'dist-tags': {'latest': '1.0.0'},
            'versions': {
                '1.0.0': {
                    'homepage': 'https://example.com'  # Non-repo URL
                }
            }
        }

        _enrich_with_repo(mp, packument)

        assert mp.repo_present_in_registry is True  # homepage present
        assert mp.repo_resolved is False
        assert mp.repo_exists is None

    def test_handles_missing_latest_version(self):
        """Test handling when latest version is missing."""
        mp = MetaPackage('testpackage')
        packument = {
            'dist-tags': {},  # No latest
            'versions': {
                '1.0.0': {
                    'repository': 'https://github.com/owner/repo'
                }
            }
        }

        _enrich_with_repo(mp, packument)

        assert mp.repo_present_in_registry is False
        assert mp.repo_resolved is False

    def test_handles_missing_version_info(self):
        """Test handling when version info is missing."""
        mp = MetaPackage('testpackage')
        packument = {
            'dist-tags': {'latest': '1.0.0'},
            'versions': {}  # No versions
        }

        _enrich_with_repo(mp, packument)

        assert mp.repo_present_in_registry is False
        assert mp.repo_resolved is False

    @patch('registry.npm.normalize_repo_url')
    @patch('registry.npm.GitHubClient')
    def test_handles_errors_gracefully(self, mock_github_client, mock_normalize):
        """Test that errors are handled gracefully."""
        # Setup mocks to raise exception
        mock_normalize.return_value = None  # Invalid URL

        mp = MetaPackage('testpackage')
        packument = {
            'dist-tags': {'latest': '1.0.0'},
            'versions': {
                '1.0.0': {
                    'repository': 'invalid-url'
                }
            }
        }

        # Should not raise exception
        _enrich_with_repo(mp, packument)

        assert mp.repo_present_in_registry is True
        assert mp.repo_resolved is False
        assert mp.repo_errors == [{'url': 'invalid-url', 'error_type': 'network', 'message': 'str'}]

    @patch('registry.npm.normalize_repo_url')
    @patch('registry.npm.GitHubClient')
    def test_handles_api_errors_gracefully(self, mock_github_client, mock_normalize):
        """Test that API errors are handled gracefully."""
        # Setup mocks
        mock_repo_ref = MagicMock()
        mock_repo_ref.normalized_url = 'https://github.com/owner/repo'
        mock_repo_ref.host = 'github'
        mock_repo_ref.owner = 'owner'
        mock_repo_ref.repo = 'repo'
        mock_normalize.return_value = mock_repo_ref

        mock_client = MagicMock()
        mock_client.get_repo.side_effect = Exception('API rate limited')
        mock_github_client.return_value = mock_client

        mp = MetaPackage('testpackage')
        packument = {
            'dist-tags': {'latest': '1.0.0'},
            'versions': {
                '1.0.0': {
                    'repository': 'https://github.com/owner/repo'
                }
            }
        }

        # Should not raise exception
        _enrich_with_repo(mp, packument)

        assert mp.repo_present_in_registry is True
        assert mp.repo_resolved is False
        assert mp.repo_errors is not None
        assert len(mp.repo_errors) == 1
        assert mp.repo_errors[0]['error_type'] == 'network'
        assert mp.repo_errors[0]['error_type'] == 'network'
        assert 'API rate limited' in mp.repo_errors[0]['message']

    @patch('registry.npm.normalize_repo_url')
    @patch('registry.npm.GitHubClient')
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

        with patch('registry.npm.VersionMatcher') as mock_matcher_class:
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

            packument = {
                'dist-tags': {'latest': '1.0.0'},
                'versions': {
                    '1.0.0': {
                        'repository': 'git+https://github.com/owner/repo.git'
                    }
                }
            }

            # Call function
            _enrich_with_repo(mp, packument)

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
        assert 'API rate limited' in mp.repo_errors[0]['message']
