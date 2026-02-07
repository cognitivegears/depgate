"""CLI entry point for the DepGate run mode (package manager wrapper).

Starts an ephemeral proxy, configures the package manager to route through it,
runs the user's command, and tears everything down.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import sys
import threading
import time
from typing import Any, List, Optional
from urllib.request import urlopen
from urllib.error import URLError

from cli_proxy import _load_policy_config, _setup_logging
from run_wrappers import get_wrapper, SUPPORTED_MANAGERS

logger = logging.getLogger(__name__)

_HEALTH_CHECK_TIMEOUT = 10  # seconds
_HEALTH_CHECK_INTERVAL = 0.1  # seconds


def _parse_run_command(args: Any) -> List[str]:
    """Extract and validate the wrapped command from parsed args.

    Returns:
        The command tokens (e.g. ["npm", "install", "lodash"]).

    Raises:
        SystemExit: If the command is empty or uses an unsupported manager.
    """
    cmd = getattr(args, "RUN_COMMAND", [])
    # Strip leading '--' separator if present
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]

    if not cmd:
        sys.stderr.write(
            "Error: No command provided.\n"
            "Usage: depgate run [options] -- <command> [args...]\n\n"
            "Supported package managers: "
            + ", ".join(SUPPORTED_MANAGERS)
            + "\n"
        )
        sys.exit(2)

    manager = os.path.basename(cmd[0]).lower()
    if manager not in SUPPORTED_MANAGERS:
        sys.stderr.write(
            f"Error: Unsupported package manager '{cmd[0]}'.\n"
            "Supported managers: "
            + ", ".join(SUPPORTED_MANAGERS)
            + "\n"
        )
        sys.exit(2)

    return cmd


class _ProxyThread(threading.Thread):
    """Runs the proxy server in a daemon thread with an asyncio event loop."""

    def __init__(self, config: Any):
        super().__init__(daemon=True)
        self._config = config
        self._server: Any = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._started = threading.Event()
        self._bound_port: Optional[int] = None
        self._error: Optional[Exception] = None

    @property
    def bound_port(self) -> Optional[int]:
        return self._bound_port

    def run(self) -> None:
        from proxy.server import RegistryProxyServer
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        async def _start():
            self._server = RegistryProxyServer(self._config)
            await self._server.start()
            self._bound_port = self._server.bound_port

        try:
            self._loop.run_until_complete(_start())
        except Exception as exc:
            self._error = exc
            self._started.set()
            return

        self._started.set()
        self._loop.run_forever()

    def wait_for_start(self, timeout: float = 10.0) -> None:
        """Block until the server is listening or an error occurred."""
        self._started.wait(timeout=timeout)
        if self._error is not None:
            raise self._error

    def shutdown(self) -> None:
        """Stop the server and event loop."""
        if self._loop is None or self._server is None:
            return

        async def _stop():
            await self._server.stop()

        # Schedule stop on the proxy's event loop
        future = asyncio.run_coroutine_threadsafe(_stop(), self._loop)
        try:
            future.result(timeout=5.0)
        except Exception:
            pass

        self._loop.call_soon_threadsafe(self._loop.stop)
        self.join(timeout=5.0)


def _wait_for_health(proxy_url: str, timeout: float = _HEALTH_CHECK_TIMEOUT) -> None:
    """Poll the proxy health endpoint until it responds.

    Args:
        proxy_url: Base proxy URL.
        timeout: Maximum seconds to wait.

    Raises:
        SystemExit: If the proxy doesn't become healthy within the timeout.
    """
    health_url = proxy_url.rstrip("/") + "/_depgate/health"
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        try:
            resp = urlopen(health_url, timeout=2)  # noqa: S310
            if resp.status == 200:
                return
        except (URLError, OSError):
            pass
        time.sleep(_HEALTH_CHECK_INTERVAL)

    sys.stderr.write("Error: Proxy server failed to start within timeout.\n")
    sys.exit(1)


def run_command(args: Any) -> None:
    """Entry point for the run mode.

    Args:
        args: Parsed CLI arguments namespace.
    """
    _setup_logging(args)

    cmd = _parse_run_command(args)

    # Lazy import proxy dependencies
    try:
        from proxy.server import ProxyConfig
    except ImportError as e:
        sys.stderr.write(
            f"Proxy server not available: {e}\n"
            "Make sure 'aiohttp' is installed: pip install aiohttp\n"
        )
        sys.exit(1)

    # Load policy config
    config_path = getattr(args, "PROXY_CONFIG", None)
    policy_config = _load_policy_config(config_path)
    if policy_config:
        logger.info("Loaded policy config from: %s", config_path)
    else:
        logger.info("No policy config loaded - all packages will be allowed")

    # Build proxy config with port=0 for ephemeral assignment
    proxy_config = ProxyConfig.from_args(args)
    proxy_config.port = 0
    proxy_config.policy_config = policy_config

    # Start proxy in background thread
    proxy_thread = _ProxyThread(proxy_config)
    proxy_thread.start()

    wrapper = None
    exit_code = 1
    try:
        proxy_thread.wait_for_start(timeout=_HEALTH_CHECK_TIMEOUT)
        port = proxy_thread.bound_port
        if port is None:
            sys.stderr.write("Error: Could not determine proxy port.\n")
            sys.exit(1)

        proxy_url = f"http://127.0.0.1:{port}"
        logger.info("Proxy started on %s", proxy_url)

        # Wait for health check
        _wait_for_health(proxy_url)

        # Build wrapper config
        manager_name = os.path.basename(cmd[0]).lower()
        wrapper = get_wrapper(manager_name, proxy_url)
        if wrapper is None:
            sys.stderr.write(
                f"Error: No wrapper config for '{cmd[0]}'.\n"
            )
            sys.exit(1)

        # Build subprocess environment
        env = os.environ.copy()
        env.update(wrapper.env_vars)

        # Build final command with extra_args injected after the manager name
        final_cmd = [cmd[0]] + wrapper.extra_args + cmd[1:]

        logger.info("Running: %s", " ".join(final_cmd))
        logger.debug("Wrapper env vars: %s", wrapper.env_vars)

        # Run the wrapped command
        result = subprocess.run(final_cmd, env=env)  # noqa: S603
        exit_code = result.returncode

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        exit_code = 130  # Standard SIGINT exit code
    finally:
        # Cleanup
        proxy_thread.shutdown()

        if wrapper:
            for temp_file in wrapper.temp_files:
                try:
                    os.unlink(temp_file)
                except OSError:
                    logger.debug("Failed to remove temp file: %s", temp_file)

    sys.exit(exit_code)
