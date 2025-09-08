"""Unit tests for repository URL normalization utilities."""
from __future__ import annotations

import pytest

from repository.url_normalize import normalize_repo_url, RepoRef


class TestNormalizeRepoUrl:
    """Test cases for URL normalization function."""

    def test_https_github_url(self):
        """Test normalization of standard HTTPS GitHub URL."""
        result = normalize_repo_url("https://github.com/owner/repo")
        assert result is not None
        assert result.normalized_url == "https://github.com/owner/repo"
        assert result.host == "github"
        assert result.owner == "owner"
        assert result.repo == "repo"
        assert result.directory is None

    def test_https_github_url_with_git_suffix(self):
        """Test normalization removes .git suffix."""
        result = normalize_repo_url("https://github.com/owner/repo.git")
        assert result is not None
        assert result.normalized_url == "https://github.com/owner/repo"
        assert result.repo == "repo"

    def test_git_plus_prefix(self):
        """Test normalization handles git+ prefix."""
        result = normalize_repo_url("git+https://github.com/owner/repo.git")
        assert result is not None
        assert result.normalized_url == "https://github.com/owner/repo"
        assert result.host == "github"

    def test_git_protocol(self):
        """Test normalization handles git:// protocol."""
        result = normalize_repo_url("git://github.com/owner/repo.git")
        assert result is not None
        assert result.normalized_url == "https://github.com/owner/repo"
        assert result.host == "github"

    def test_ssh_style_url(self):
        """Test normalization handles SSH-style git@host:owner/repo."""
        result = normalize_repo_url("git@github.com:owner/repo.git")
        assert result is not None
        assert result.normalized_url == "https://github.com/owner/repo"
        assert result.host == "github"

    def test_ssh_protocol_url(self):
        """Test normalization handles SSH protocol."""
        result = normalize_repo_url("ssh://git@github.com/owner/repo.git")
        assert result is not None
        assert result.normalized_url == "https://github.com/owner/repo"
        assert result.host == "github"

    def test_gitlab_url(self):
        """Test normalization detects GitLab host."""
        result = normalize_repo_url("https://gitlab.com/owner/repo")
        assert result is not None
        assert result.host == "gitlab"
        assert result.normalized_url == "https://gitlab.com/owner/repo"

    def test_other_host(self):
        """Test normalization handles non-GitHub/GitLab hosts."""
        result = normalize_repo_url("https://bitbucket.org/owner/repo")
        assert result is not None
        assert result.host == "other"
        assert result.normalized_url == "https://bitbucket.org/owner/repo"

    def test_case_insensitive_host(self):
        """Test host detection is case insensitive."""
        result = normalize_repo_url("https://GITHUB.COM/owner/repo")
        assert result is not None
        assert result.host == "github"
        assert result.normalized_url == "https://github.com/owner/repo"

    def test_directory_hint(self):
        """Test directory hint preservation."""
        result = normalize_repo_url("https://github.com/owner/repo", directory="packages/my-package")
        assert result is not None
        assert result.directory == "packages/my-package"

    def test_empty_url(self):
        """Test empty URL returns None."""
        result = normalize_repo_url("")
        assert result is None

    def test_none_url(self):
        """Test None URL returns None."""
        result = normalize_repo_url(None)
        assert result is None

    def test_malformed_url(self):
        """Test malformed URL returns None."""
        result = normalize_repo_url("not-a-url")
        assert result is None

    def test_url_without_repo(self):
        """Test URL without repository part returns None."""
        result = normalize_repo_url("https://github.com/owner")
        assert result is None


class TestRepoRef:
    """Test cases for RepoRef dataclass."""

    def test_creation(self):
        """Test RepoRef creation with all fields."""
        ref = RepoRef(
            normalized_url="https://github.com/owner/repo",
            host="github",
            owner="owner",
            repo="repo",
            directory="packages/my-package"
        )
        assert ref.normalized_url == "https://github.com/owner/repo"
        assert ref.host == "github"
        assert ref.owner == "owner"
        assert ref.repo == "repo"
        assert ref.directory == "packages/my-package"

    def test_creation_minimal(self):
        """Test RepoRef creation with minimal fields."""
        ref = RepoRef(
            normalized_url="https://github.com/owner/repo",
            host="github",
            owner="owner",
            repo="repo"
        )
        assert ref.directory is None
