"""Tests for cli_run — the depgate run mode orchestrator."""

import os
import sys
import types
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from src.args import parse_args
from src.run_wrappers import WrapperConfig


class TestRunArgParsing:
    """Tests for 'depgate run' CLI argument parsing."""

    def test_basic_command(self):
        ns = parse_args(["run", "npm", "install", "lodash"])
        assert ns.action == "run"
        assert ns.RUN_COMMAND == ["npm", "install", "lodash"]

    def test_with_separator(self):
        ns = parse_args(["run", "--", "npm", "install", "lodash"])
        assert ns.action == "run"
        assert ns.RUN_COMMAND == ["--", "npm", "install", "lodash"]

    def test_with_config(self):
        ns = parse_args(["run", "--config", "policy.yml", "pip", "install", "requests"])
        assert ns.PROXY_CONFIG == "policy.yml"
        assert ns.RUN_COMMAND == ["pip", "install", "requests"]

    def test_with_decision_mode(self):
        ns = parse_args(["run", "--decision-mode", "warn", "npm", "install"])
        assert ns.PROXY_DECISION_MODE == "warn"

    def test_with_log_level(self):
        ns = parse_args(["run", "--log-level", "DEBUG", "npm", "install"])
        assert ns.LOG_LEVEL == "DEBUG"

    def test_with_upstream_overrides(self):
        ns = parse_args([
            "run",
            "--upstream-npm", "http://custom-npm:8080",
            "--upstream-pypi", "http://custom-pypi:8080",
            "npm", "install",
        ])
        assert ns.PROXY_UPSTREAM_NPM == "http://custom-npm:8080"
        assert ns.PROXY_UPSTREAM_PYPI == "http://custom-pypi:8080"

    def test_with_timeout(self):
        ns = parse_args(["run", "--timeout", "60", "npm", "install"])
        assert ns.PROXY_TIMEOUT == 60

    def test_defaults(self):
        ns = parse_args(["run", "npm", "install"])
        assert ns.PROXY_DECISION_MODE == "block"
        assert ns.LOG_LEVEL == "INFO"
        assert ns.PROXY_TIMEOUT == 30

    def test_empty_remainder(self):
        ns = parse_args(["run"])
        assert ns.RUN_COMMAND == []

    def test_with_logfile(self):
        ns = parse_args(["run", "--logfile", "/tmp/test.log", "npm", "install"])
        assert ns.LOG_FILE == "/tmp/test.log"


class TestParseRunCommand:
    """Tests for _parse_run_command validation."""

    def test_empty_command_exits(self):
        from src.cli_run import _parse_run_command
        args = MagicMock()
        args.RUN_COMMAND = []
        with pytest.raises(SystemExit) as exc_info:
            _parse_run_command(args)
        assert exc_info.value.code == 2

    def test_unsupported_manager_exits(self):
        from src.cli_run import _parse_run_command
        args = MagicMock()
        args.RUN_COMMAND = ["conda", "install", "numpy"]
        with pytest.raises(SystemExit) as exc_info:
            _parse_run_command(args)
        assert exc_info.value.code == 2

    def test_supported_manager_returns_command(self):
        from src.cli_run import _parse_run_command
        args = MagicMock()
        args.RUN_COMMAND = ["npm", "install", "lodash"]
        result = _parse_run_command(args)
        assert result == ["npm", "install", "lodash"]

    def test_strips_double_dash(self):
        from src.cli_run import _parse_run_command
        args = MagicMock()
        args.RUN_COMMAND = ["--", "pip", "install", "requests"]
        result = _parse_run_command(args)
        assert result == ["pip", "install", "requests"]

    def test_only_double_dash_exits(self):
        from src.cli_run import _parse_run_command
        args = MagicMock()
        args.RUN_COMMAND = ["--"]
        with pytest.raises(SystemExit):
            _parse_run_command(args)


class TestRunCommand:
    """Tests for run_command orchestration."""

    def _make_args(self, cmd, config=None, decision_mode="block"):
        args = MagicMock()
        args.RUN_COMMAND = cmd
        args.PROXY_CONFIG = config
        args.PROXY_DECISION_MODE = decision_mode
        args.PROXY_HOST = "127.0.0.1"
        args.PROXY_PORT = 8080  # will be overridden to 0
        args.PROXY_TIMEOUT = 30
        args.PROXY_CACHE_TTL = 3600
        args.PROXY_RESPONSE_CACHE_TTL = 300
        args.PROXY_ALLOW_EXTERNAL = False
        args.PROXY_CLIENT_MAX_SIZE = 10 * 1024 * 1024
        args.PROXY_UPSTREAM_NPM = None
        args.PROXY_UPSTREAM_PYPI = None
        args.PROXY_UPSTREAM_MAVEN = None
        args.PROXY_UPSTREAM_NUGET = None
        args.LOG_LEVEL = "WARNING"
        args.LOG_FILE = None
        return args

    @patch("src.cli_run.subprocess.run")
    @patch("src.cli_run._wait_for_health")
    @patch("src.cli_run._ProxyThread")
    @patch("src.cli_run._load_policy_config", return_value={})
    @patch("src.cli_run._setup_logging")
    def test_successful_run_propagates_exit_code(
        self, mock_logging, mock_load, mock_thread_cls, mock_health, mock_subproc
    ):
        mock_thread = MagicMock()
        mock_thread.bound_port = 12345
        mock_thread.error = None
        mock_thread_cls.return_value = mock_thread
        mock_subproc.return_value = MagicMock(returncode=0)

        args = self._make_args(["npm", "install", "lodash"])

        with pytest.raises(SystemExit) as exc_info:
            from src.cli_run import run_command
            run_command(args)

        assert exc_info.value.code == 0
        mock_subproc.assert_called_once()
        mock_thread.shutdown.assert_called_once()

    @patch("src.cli_run.subprocess.run")
    @patch("src.cli_run._wait_for_health")
    @patch("src.cli_run._ProxyThread")
    @patch("src.cli_run._load_policy_config", return_value={})
    @patch("src.cli_run._setup_logging")
    def test_nonzero_exit_code_propagated(
        self, mock_logging, mock_load, mock_thread_cls, mock_health, mock_subproc
    ):
        mock_thread = MagicMock()
        mock_thread.bound_port = 12345
        mock_thread.error = None
        mock_thread_cls.return_value = mock_thread
        mock_subproc.return_value = MagicMock(returncode=42)

        args = self._make_args(["npm", "install", "bad-package"])

        with pytest.raises(SystemExit) as exc_info:
            from src.cli_run import run_command
            run_command(args)

        assert exc_info.value.code == 42

    @patch("src.cli_run.subprocess.run")
    @patch("src.cli_run._wait_for_health")
    @patch("src.cli_run._ProxyThread")
    @patch("src.cli_run._load_policy_config", return_value={})
    @patch("src.cli_run._setup_logging")
    def test_env_vars_set_on_subprocess(
        self, mock_logging, mock_load, mock_thread_cls, mock_health, mock_subproc
    ):
        mock_thread = MagicMock()
        mock_thread.bound_port = 12345
        mock_thread.error = None
        mock_thread_cls.return_value = mock_thread
        mock_subproc.return_value = MagicMock(returncode=0)

        args = self._make_args(["npm", "install", "lodash"])

        with pytest.raises(SystemExit):
            from src.cli_run import run_command
            run_command(args)

        call_kwargs = mock_subproc.call_args
        env = call_kwargs.kwargs.get("env") or call_kwargs[1].get("env")
        assert env["npm_config_registry"] == "http://127.0.0.1:12345"

    @patch("src.cli_run.subprocess.run")
    @patch("src.cli_run._wait_for_health")
    @patch("src.cli_run._ProxyThread")
    @patch("src.cli_run._load_policy_config", return_value={})
    @patch("src.cli_run._setup_logging")
    def test_extra_args_injected(
        self, mock_logging, mock_load, mock_thread_cls, mock_health, mock_subproc
    ):
        """Maven wrapper injects -s <settings.xml> after the command name."""
        mock_thread = MagicMock()
        mock_thread.bound_port = 12345
        mock_thread.error = None
        mock_thread_cls.return_value = mock_thread
        mock_subproc.return_value = MagicMock(returncode=0)

        args = self._make_args(["mvn", "clean", "install"])

        with pytest.raises(SystemExit):
            from src.cli_run import run_command
            run_command(args)

        call_args = mock_subproc.call_args[0][0]
        assert call_args[0] == "mvn"
        assert "-s" in call_args
        # user args come after the injected args
        assert "clean" in call_args
        assert "install" in call_args

    @patch("src.cli_run.subprocess.run")
    @patch("src.cli_run._wait_for_health")
    @patch("src.cli_run._ProxyThread")
    @patch("src.cli_run._load_policy_config", return_value={})
    @patch("src.cli_run._setup_logging")
    def test_temp_files_cleaned_up(
        self, mock_logging, mock_load, mock_thread_cls, mock_health, mock_subproc
    ):
        """Temp files from wrappers (e.g. Maven settings.xml) are cleaned up."""
        mock_thread = MagicMock()
        mock_thread.bound_port = 12345
        mock_thread.error = None
        mock_thread_cls.return_value = mock_thread
        mock_subproc.return_value = MagicMock(returncode=0)

        args = self._make_args(["mvn", "clean", "install"])

        with pytest.raises(SystemExit):
            from src.cli_run import run_command
            run_command(args)

        # Extract the temp file path from the subprocess call
        call_args = mock_subproc.call_args[0][0]
        s_idx = call_args.index("-s")
        temp_path = call_args[s_idx + 1]
        # File should have been cleaned up
        assert not os.path.exists(temp_path)

    @patch("src.cli_run._ProxyThread")
    @patch("src.cli_run._load_policy_config", return_value={})
    @patch("src.cli_run._setup_logging")
    def test_no_port_exits(
        self, mock_logging, mock_load, mock_thread_cls
    ):
        """Exit if bound_port is None (server didn't bind)."""
        mock_thread = MagicMock()
        mock_thread.bound_port = None
        mock_thread.error = None
        mock_thread_cls.return_value = mock_thread

        args = self._make_args(["npm", "install"])

        with pytest.raises(SystemExit) as exc_info:
            from src.cli_run import run_command
            run_command(args)

        assert exc_info.value.code == 1

    @patch("src.cli_run.subprocess.run", side_effect=FileNotFoundError())
    @patch("src.cli_run._wait_for_health")
    @patch("src.cli_run._ProxyThread")
    @patch("src.cli_run._load_policy_config", return_value={})
    @patch("src.cli_run._setup_logging")
    def test_missing_binary_exits_127(
        self, mock_logging, mock_load, mock_thread_cls, mock_health, mock_subproc, capsys
    ):
        mock_thread = MagicMock()
        mock_thread.bound_port = 12345
        mock_thread.error = None
        mock_thread_cls.return_value = mock_thread

        args = self._make_args(["npm", "install", "lodash"])

        with pytest.raises(SystemExit) as exc_info:
            from src.cli_run import run_command
            run_command(args)

        assert exc_info.value.code == 127
        stderr = capsys.readouterr().err
        assert "Command not found" in stderr

    @patch("src.cli_run._ProxyThread")
    @patch("src.cli_run._load_policy_config", return_value={})
    @patch("src.cli_run._setup_logging")
    def test_proxy_start_timeout_exits(
        self, mock_logging, mock_load, mock_thread_cls, capsys
    ):
        mock_thread = MagicMock()
        mock_thread.wait_for_start.side_effect = TimeoutError("timeout")
        mock_thread.error = None
        mock_thread_cls.return_value = mock_thread

        args = self._make_args(["npm", "install"])

        with pytest.raises(SystemExit) as exc_info:
            from src.cli_run import run_command
            run_command(args)

        assert exc_info.value.code == 1
        stderr = capsys.readouterr().err
        assert "failed to start within" in stderr.lower()


class TestWaitForHealth:
    """Tests for the health check polling."""

    @patch("src.cli_run.urlopen")
    def test_healthy_proxy(self, mock_urlopen):
        from src.cli_run import _wait_for_health
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_urlopen.return_value.__enter__.return_value = mock_resp
        # Should not raise
        _wait_for_health("http://127.0.0.1:12345", timeout=1)

    @patch("src.cli_run.urlopen")
    def test_timeout_exits(self, mock_urlopen):
        from src.cli_run import _wait_for_health
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("refused")
        with pytest.raises(SystemExit) as exc_info:
            _wait_for_health("http://127.0.0.1:12345", timeout=0.3)
        assert exc_info.value.code == 1
