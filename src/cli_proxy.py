"""CLI entry point for the DepGate proxy server.

This module provides the command-line interface for starting the proxy server
that intercepts package manager requests and evaluates them against policies.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict, Optional

from common.logging_utils import configure_logging

logger = logging.getLogger(__name__)


def _load_policy_config(config_path: Optional[str]) -> Dict[str, Any]:
    """Load policy configuration from file.

    Args:
        config_path: Path to YAML/JSON config file.

    Returns:
        Policy configuration dict.
    """
    if not config_path:
        return {}

    if not os.path.isfile(config_path):
        logger.warning(f"Config file not found: {config_path}")
        return {}

    try:
        import yaml

        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if isinstance(data, dict):
                # Extract policy section if present
                return data.get("policy", data)
            return {}
    except ImportError:
        # Fall back to JSON
        import json

        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data.get("policy", data)
            return {}
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return {}


def _setup_logging(args: Any) -> None:
    """Configure logging based on CLI arguments.

    Args:
        args: Parsed CLI arguments.
    """
    # Honor CLI --log-level
    if getattr(args, "LOG_LEVEL", None):
        os.environ["DEPGATE_LOG_LEVEL"] = str(args.LOG_LEVEL).upper()

    configure_logging()

    # Apply CLI log level
    try:
        level_name = str(getattr(args, "LOG_LEVEL", "INFO")).upper()
        level_value = getattr(logging, level_name, logging.INFO)
        logging.getLogger().setLevel(level_value)
    except Exception:
        pass


def run_proxy_server(args: Any) -> None:
    """Entry point for the proxy server command.

    Args:
        args: Parsed CLI arguments namespace.
    """
    _setup_logging(args)

    # Lazy import to avoid loading aiohttp for other commands
    try:
        from proxy.server import RegistryProxyServer, ProxyConfig, run_proxy_server_sync
    except ImportError as e:
        sys.stderr.write(
            f"Proxy server not available: {e}\n"
            "Make sure 'aiohttp' is installed: pip install aiohttp\n"
        )
        sys.exit(1)

    # Load policy configuration
    config_path = getattr(args, "PROXY_CONFIG", None)
    policy_config = _load_policy_config(config_path)

    if policy_config:
        logger.info(f"Loaded policy config from: {config_path}")
    else:
        logger.info("No policy config loaded - all packages will be allowed")

    # Create server config
    config = ProxyConfig.from_args(args)
    config.policy_config = policy_config

    # Print startup banner
    print(
        f"\n"
        f"  DepGate Proxy Server\n"
        f"  ====================\n"
        f"  Listening: http://{config.host}:{config.port}\n"
        f"  Mode: {config.decision_mode}\n"
        f"\n"
        f"  Configure your package manager:\n"
        f"    npm config set registry http://{config.host}:{config.port}\n"
        f"    pip config set global.index-url http://{config.host}:{config.port}/simple\n"
        f"\n"
        f"  Press Ctrl+C to stop\n"
    )

    # Run the server
    run_proxy_server_sync(config)
