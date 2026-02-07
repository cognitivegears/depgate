"""Tests for run_wrappers — per-manager wrapper configurations."""

import os
import pytest
from unittest.mock import patch

from src.run_wrappers import (
    get_wrapper,
    WrapperConfig,
    SUPPORTED_MANAGERS,
    _SETTINGS_XML_TEMPLATE,
    _INIT_GRADLE_TEMPLATE,
    _NUGET_CONFIG_TEMPLATE,
)

PROXY_URL = "http://127.0.0.1:54321"


class TestGetWrapper:
    """Tests for the get_wrapper() dispatcher."""

    def test_unrecognized_command_returns_none(self):
        assert get_wrapper("conda", PROXY_URL) is None

    def test_unrecognized_path_returns_none(self):
        assert get_wrapper("/usr/local/bin/conda", PROXY_URL) is None

    def test_all_supported_managers_return_config(self):
        for mgr in SUPPORTED_MANAGERS:
            result = get_wrapper(mgr, PROXY_URL)
            assert result is not None, f"get_wrapper returned None for {mgr}"
            assert isinstance(result, WrapperConfig)
            assert result.registry_type != ""


class TestNpmWrapper:
    """Tests for npm wrapper."""

    def test_env_vars(self):
        cfg = get_wrapper("npm", PROXY_URL)
        assert cfg.env_vars == {"npm_config_registry": PROXY_URL}
        assert cfg.extra_args == []
        assert cfg.temp_files == []
        assert cfg.registry_type == "npm"


class TestPnpmWrapper:
    """Tests for pnpm wrapper."""

    def test_env_vars(self):
        cfg = get_wrapper("pnpm", PROXY_URL)
        assert cfg.env_vars == {"npm_config_registry": PROXY_URL}
        assert cfg.registry_type == "npm"


class TestYarnWrapper:
    """Tests for yarn wrapper."""

    def test_env_vars(self):
        cfg = get_wrapper("yarn", PROXY_URL)
        assert cfg.env_vars["npm_config_registry"] == PROXY_URL
        assert cfg.env_vars["YARN_NPM_REGISTRY_SERVER"] == PROXY_URL
        assert cfg.registry_type == "npm"


class TestBunWrapper:
    """Tests for bun wrapper."""

    def test_env_vars(self):
        cfg = get_wrapper("bun", PROXY_URL)
        assert cfg.env_vars == {"npm_config_registry": PROXY_URL}
        assert cfg.registry_type == "npm"


class TestPipWrapper:
    """Tests for pip/pip3/pipx wrappers."""

    def test_pip_env_vars(self):
        cfg = get_wrapper("pip", PROXY_URL)
        assert cfg.env_vars["PIP_INDEX_URL"] == PROXY_URL + "/simple"
        assert cfg.env_vars["PIP_TRUSTED_HOST"] == "127.0.0.1"
        assert cfg.registry_type == "pypi"

    def test_pip3_same_as_pip(self):
        cfg = get_wrapper("pip3", PROXY_URL)
        assert cfg.env_vars["PIP_INDEX_URL"] == PROXY_URL + "/simple"
        assert cfg.registry_type == "pypi"

    def test_pipx_same_as_pip(self):
        cfg = get_wrapper("pipx", PROXY_URL)
        assert cfg.env_vars["PIP_INDEX_URL"] == PROXY_URL + "/simple"
        assert cfg.registry_type == "pypi"


class TestPoetryWrapper:
    """Tests for poetry wrapper."""

    def test_env_vars(self):
        cfg = get_wrapper("poetry", PROXY_URL)
        assert cfg.env_vars["PIP_INDEX_URL"] == PROXY_URL + "/simple"
        assert cfg.env_vars["PIP_TRUSTED_HOST"] == "127.0.0.1"
        assert cfg.registry_type == "pypi"


class TestUvWrapper:
    """Tests for uv wrapper."""

    def test_env_vars(self):
        cfg = get_wrapper("uv", PROXY_URL)
        assert cfg.env_vars["UV_INDEX_URL"] == PROXY_URL + "/simple"
        assert cfg.env_vars["UV_INSECURE_HOST"] == "127.0.0.1"
        assert cfg.registry_type == "pypi"

    def test_no_pip_vars(self):
        cfg = get_wrapper("uv", PROXY_URL)
        assert "PIP_INDEX_URL" not in cfg.env_vars


class TestMavenWrapper:
    """Tests for mvn wrapper."""

    def test_creates_settings_xml(self):
        cfg = get_wrapper("mvn", PROXY_URL)
        assert cfg.registry_type == "maven"
        assert len(cfg.temp_files) == 1
        assert cfg.temp_files[0].endswith(".xml")
        assert cfg.extra_args == ["-s", cfg.temp_files[0]]

        # Verify file content
        with open(cfg.temp_files[0], "r") as f:
            content = f.read()
        assert PROXY_URL in content
        assert "<mirrorOf>*</mirrorOf>" in content

        # Cleanup
        os.unlink(cfg.temp_files[0])

    def test_no_env_vars(self):
        cfg = get_wrapper("mvn", PROXY_URL)
        assert cfg.env_vars == {}
        # Cleanup
        for f in cfg.temp_files:
            os.unlink(f)

    @patch("src.run_wrappers.os.path.exists", return_value=True)
    def test_warns_when_user_settings_exist(self, mock_exists, caplog):
        import logging
        with caplog.at_level(logging.WARNING, logger="src.run_wrappers"):
            cfg = get_wrapper("mvn", PROXY_URL)
        assert "~/.m2/settings.xml" in caplog.text
        for f in cfg.temp_files:
            os.unlink(f)


class TestGradleWrapper:
    """Tests for gradle/gradlew wrapper."""

    def test_creates_init_gradle(self):
        cfg = get_wrapper("gradle", PROXY_URL)
        assert cfg.registry_type == "maven"
        assert len(cfg.temp_files) == 1
        assert cfg.temp_files[0].endswith(".gradle")
        assert cfg.extra_args == ["--init-script", cfg.temp_files[0]]

        # Verify file content
        with open(cfg.temp_files[0], "r") as f:
            content = f.read()
        assert PROXY_URL in content
        assert "allowInsecureProtocol true" in content

        # Cleanup
        os.unlink(cfg.temp_files[0])

    def test_gradlew_same_as_gradle(self):
        cfg = get_wrapper("gradlew", PROXY_URL)
        assert cfg.registry_type == "maven"
        assert len(cfg.temp_files) == 1
        # Cleanup
        os.unlink(cfg.temp_files[0])


class TestNugetWrapper:
    """Tests for dotnet/nuget wrapper."""

    def test_dotnet_creates_config(self):
        cfg = get_wrapper("dotnet", PROXY_URL)
        assert cfg.registry_type == "nuget"
        assert len(cfg.temp_files) == 1
        assert "NUGET_CONFIGFILE" in cfg.env_vars
        assert cfg.env_vars["NUGET_CONFIGFILE"] == cfg.temp_files[0]

        # Verify file content
        with open(cfg.temp_files[0], "r") as f:
            content = f.read()
        assert PROXY_URL in content
        assert "depgate-proxy" in content
        assert "<clear />" in content

        # Cleanup
        os.unlink(cfg.temp_files[0])

    def test_nuget_same_as_dotnet(self):
        cfg = get_wrapper("nuget", PROXY_URL)
        assert cfg.registry_type == "nuget"
        assert len(cfg.temp_files) == 1
        # Cleanup
        os.unlink(cfg.temp_files[0])


class TestEdgeCases:
    """Edge case tests."""

    def test_path_based_command(self):
        """get_wrapper extracts basename from full paths."""
        cfg = get_wrapper("/usr/local/bin/npm", PROXY_URL)
        assert cfg is not None
        assert cfg.registry_type == "npm"

    def test_trailing_slash_proxy_url(self):
        """Trailing slash on proxy URL is handled."""
        cfg = get_wrapper("pip", PROXY_URL + "/")
        assert cfg.env_vars["PIP_INDEX_URL"] == PROXY_URL + "/simple"
