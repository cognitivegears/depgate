"""CLI configuration overrides for runtime tunables (e.g., deps.dev flags).

Extracted from depgate.py to keep the entrypoint slim. Applies CLI overrides
with highest precedence and never raises to avoid breaking the CLI.
"""

from __future__ import annotations

from constants import Constants


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
