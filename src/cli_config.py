"""CLI configuration overrides for runtime tunables (e.g., deps.dev flags).

Extracted from depgate.py to keep the entrypoint slim. Applies CLI overrides
with highest precedence and never raises to avoid breaking the CLI.
"""

from __future__ import annotations

import logging
import subprocess
import os
from typing import Optional

from constants import Constants

logger = logging.getLogger(__name__)


def apply_depsdev_overrides(args) -> None:
    """Apply CLI overrides for deps.dev feature flags and tunables.

    This mirrors the original behavior from depgate.py and is intentionally
    defensive: any exception is swallowed to avoid breaking the CLI.
    """
    try:
        if getattr(args, "DEPSDEV_DISABLE", False):
            Constants.DEPSDEV_ENABLED = False  # type: ignore[attr-defined]
        if getattr(args, "DEPSDEV_BASE_URL", None):
            Constants.DEPSDEV_BASE_URL = args.DEPSDEV_BASE_URL  # type: ignore[attr-defined]
        if getattr(args, "DEPSDEV_CACHE_TTL", None) is not None:
            Constants.DEPSDEV_CACHE_TTL_SEC = int(args.DEPSDEV_CACHE_TTL)  # type: ignore[attr-defined]
        if getattr(args, "DEPSDEV_MAX_CONCURRENCY", None) is not None:
            Constants.DEPSDEV_MAX_CONCURRENCY = int(args.DEPSDEV_MAX_CONCURRENCY)  # type: ignore[attr-defined]
        if getattr(args, "DEPSDEV_MAX_RESPONSE_BYTES", None) is not None:
            Constants.DEPSDEV_MAX_RESPONSE_BYTES = int(args.DEPSDEV_MAX_RESPONSE_BYTES)  # type: ignore[attr-defined]
        if getattr(args, "DEPSDEV_STRICT_OVERRIDE", False):
            Constants.DEPSDEV_STRICT_OVERRIDE = True  # type: ignore[attr-defined]
    except Exception:  # pylint: disable=broad-exception-caught
        # Defensive: never break CLI on config overrides
        pass


def get_osm_token() -> Optional[str]:
    """Get OpenSourceMalware API token from various sources in priority order.

    Priority:
    1. CLI argument (handled in apply_osm_overrides)
    2. Environment variable DEPGATE_OSM_API_TOKEN
    3. Command execution: config token_command (YAML config only, not from env var for security)
    4. YAML config (already loaded into Constants.OSM_API_TOKEN)

    Note: Command execution is only allowed from trusted sources (CLI args and YAML config),
    not from environment variables to prevent arbitrary command execution.

    Returns:
        API token string or None if not available
    """
    # Check environment variable
    env_token = os.environ.get("DEPGATE_OSM_API_TOKEN")
    if env_token and env_token.strip():
        return env_token.strip()

    # Check command execution (from YAML config only - trusted source)
    # Security: Do NOT read from environment variable to prevent arbitrary command execution
    token_command = None
    if hasattr(Constants, "OSM_TOKEN_COMMAND") and Constants.OSM_TOKEN_COMMAND:  # type: ignore[attr-defined]
        token_command = Constants.OSM_TOKEN_COMMAND  # type: ignore[attr-defined]

    if token_command:
        try:
            result = subprocess.run(
                token_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if result.returncode == 0 and result.stdout:
                token = result.stdout.strip()
                if token:
                    return token
        except Exception as exc:  # pylint: disable=broad-exception-caught
            logger.debug("Failed to execute token command: %s", exc)

    # Check Constants (loaded from YAML config)
    if hasattr(Constants, "OSM_API_TOKEN") and Constants.OSM_API_TOKEN:  # type: ignore[attr-defined]
        return Constants.OSM_API_TOKEN  # type: ignore[attr-defined]

    return None


def apply_osm_overrides(args) -> None:
    """Apply CLI overrides for OpenSourceMalware feature flags and tunables.

    This mirrors the deps.dev override pattern and is intentionally
    defensive: any exception is swallowed to avoid breaking the CLI.
    """
    try:
        # Check if disabled
        if getattr(args, "OSM_DISABLE", False):
            Constants.OSM_ENABLED = False  # type: ignore[attr-defined]
            return

        # Get token from CLI args (highest priority)
        # Priority: 1. CLI --osm-api-token, 2. CLI --osm-token-command, 3. Other sources
        cli_token = getattr(args, "OSM_API_TOKEN", None)
        if cli_token:
            Constants.OSM_API_TOKEN = cli_token  # type: ignore[attr-defined]
            Constants.OSM_ENABLED = True  # type: ignore[attr-defined]
        else:
            # Check CLI token command (second priority)
            token_cmd = getattr(args, "OSM_TOKEN_COMMAND", None)
            if token_cmd:
                try:
                    result = subprocess.run(
                        token_cmd,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=10,
                        check=False,
                    )
                    if result.returncode == 0 and result.stdout:
                        token = result.stdout.strip()
                        if token:
                            Constants.OSM_API_TOKEN = token  # type: ignore[attr-defined]
                            Constants.OSM_ENABLED = True  # type: ignore[attr-defined]
                        else:
                            logger.warning(
                                "OSM token command '%s' executed successfully but returned empty output",
                                token_cmd
                            )
                    else:
                        error_msg = result.stderr.strip() if result.stderr else f"exit code {result.returncode}"
                        logger.warning(
                            "OSM token command '%s' failed: %s",
                            token_cmd,
                            error_msg
                        )
                except subprocess.TimeoutExpired:
                    logger.warning("OSM token command '%s' timed out after 10 seconds", token_cmd)
                except Exception as exc:  # pylint: disable=broad-exception-caught
                    logger.warning("Failed to execute OSM token command '%s': %s", token_cmd, exc)

            # If still no token, try other sources (env var, config token_command, YAML)
            if not getattr(Constants, "OSM_API_TOKEN", None):  # type: ignore[attr-defined]
                token = get_osm_token()
                if token:
                    Constants.OSM_API_TOKEN = token  # type: ignore[attr-defined]
                    Constants.OSM_ENABLED = True  # type: ignore[attr-defined]

            # If still no token, disable and warn
            if not getattr(Constants, "OSM_API_TOKEN", None):  # type: ignore[attr-defined]
                was_enabled = getattr(Constants, "OSM_ENABLED", False)  # type: ignore[attr-defined]
                Constants.OSM_ENABLED = False  # type: ignore[attr-defined]
                # Show warning if it was enabled, or show info message if disabled by default
                if was_enabled:
                    logger.warning(
                        "OpenSourceMalware API token not available. "
                        "Set DEPGATE_OSM_API_TOKEN environment variable, "
                        "use --osm-api-token, or configure in YAML. "
                        "Disabling OpenSourceMalware checks."
                    )
                else:
                    # Warn user that OSM checks are not available (one-time warning message)
                    logger.warning(
                        "OpenSourceMalware checks are disabled (API token not available). "
                        "To enable, set DEPGATE_OSM_API_TOKEN environment variable, "
                        "use --osm-api-token, use --osm-token-command, or configure in YAML config."
                    )

        # Apply other CLI overrides
        if getattr(args, "OSM_BASE_URL", None):
            Constants.OSM_API_BASE_URL = args.OSM_BASE_URL  # type: ignore[attr-defined]
        if getattr(args, "OSM_CACHE_TTL", None) is not None:
            Constants.OSM_CACHE_TTL_SEC = int(args.OSM_CACHE_TTL)  # type: ignore[attr-defined]
        if getattr(args, "OSM_AUTH_METHOD", None):
            auth_method = args.OSM_AUTH_METHOD.lower()
            if auth_method in ("header", "query"):
                Constants.OSM_AUTH_METHOD = auth_method  # type: ignore[attr-defined]
        if getattr(args, "OSM_MAX_RETRIES", None) is not None:
            Constants.OSM_MAX_RETRIES = int(args.OSM_MAX_RETRIES)  # type: ignore[attr-defined]

    except Exception:  # pylint: disable=broad-exception-caught
        # Defensive: never break CLI on config overrides
        pass
