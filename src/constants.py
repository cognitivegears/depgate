"""Constants used in the project."""

from enum import Enum
import os
import platform
from typing import Any, Dict, Optional

# Optional YAML support (config file). If unavailable, config loading is skipped gracefully.
try:
    import yaml  # type: ignore
except Exception:  # pylint: disable=broad-exception-caught
    yaml = None  # type: ignore[assignment]  # pylint: disable=invalid-name


class ExitCodes(Enum):
    """Exit codes for the program.

    Args:
        Enum (int): Exit codes for the program.
    """

    SUCCESS = 0
    CONNECTION_ERROR = 2
    FILE_ERROR = 1
    EXIT_WARNINGS = 3


class PackageManagers(Enum):
    """Package managers supported by the program.

    Args:
        Enum (string): Package managers supported by the program.
    """

    NPM = "npm"
    PYPI = "pypi"
    MAVEN = "maven"


class DefaultHeuristics(Enum):
    """Default heuristics for the program.

    Args:
        Enum (int): Default heuristics for the program.
    """

    MIN_VERSIONS = 2
    NEW_DAYS_THRESHOLD = 2
    SCORE_THRESHOLD = 0.6
    RISKY_THRESHOLD = 0.15


class Constants:  # pylint: disable=too-few-public-methods
    """General constants used in the project.
    Data holder for configuration constants; not intended to provide behavior.
    """

    REGISTRY_URL_PYPI = "https://pypi.org/pypi/"
    REGISTRY_URL_NPM = "https://registry.npmjs.org/"
    REGISTRY_URL_NPM_STATS = "https://api.npms.io/v2/package/mget"
    REGISTRY_URL_MAVEN = "https://search.maven.org/solrsearch/select"
    SUPPORTED_PACKAGES = [
        PackageManagers.NPM.value,
        PackageManagers.PYPI.value,
        PackageManagers.MAVEN.value,
    ]
    LEVELS = ["compare", "comp", "heuristics", "heur", "policy", "pol", "linked"]
    REQUIREMENTS_FILE = "requirements.txt"
    PACKAGE_JSON_FILE = "package.json"
    POM_XML_FILE = "pom.xml"
    PYPROJECT_TOML_FILE = "pyproject.toml"
    UV_LOCK_FILE = "uv.lock"
    POETRY_LOCK_FILE = "poetry.lock"
    LOG_FORMAT = "[%(levelname)s] %(message)s"  # Added LOG_FORMAT constant
    ANALYSIS = "[ANALYSIS]"
    REQUEST_TIMEOUT = 30  # Timeout in seconds for all HTTP requests

    # Repository API constants
    GITHUB_API_BASE = "https://api.github.com"
    GITLAB_API_BASE = "https://gitlab.com/api/v4"
    READTHEDOCS_API_BASE = "https://readthedocs.org/api/v3"
    ENV_GITHUB_TOKEN = "GITHUB_TOKEN"
    ENV_GITLAB_TOKEN = "GITLAB_TOKEN"
    REPO_API_PER_PAGE = 100
    HTTP_RETRY_MAX = 3
    HTTP_RETRY_BASE_DELAY_SEC = 0.3
    HTTP_CACHE_TTL_SEC = 300

    # deps.dev integration defaults
    DEPSDEV_ENABLED: bool = True
    DEPSDEV_BASE_URL = "https://api.deps.dev/v3"
    DEPSDEV_MAX_CONCURRENCY = 4
    DEPSDEV_CACHE_TTL_SEC = 86400
    DEPSDEV_MAX_RESPONSE_BYTES = 1048576
    DEPSDEV_STRICT_OVERRIDE: bool = False

    # HTTP rate limit and retry policy defaults (fail-fast to preserve existing behavior)
    HTTP_RATE_POLICY_DEFAULT_MAX_RETRIES = 0
    HTTP_RATE_POLICY_DEFAULT_INITIAL_BACKOFF_SEC = 0.5
    HTTP_RATE_POLICY_DEFAULT_MULTIPLIER = 2.0
    HTTP_RATE_POLICY_DEFAULT_JITTER_PCT = 0.2
    HTTP_RATE_POLICY_DEFAULT_MAX_BACKOFF_SEC = 60.0
    HTTP_RATE_POLICY_DEFAULT_TOTAL_RETRY_TIME_CAP_SEC = 120.0
    HTTP_RATE_POLICY_DEFAULT_STRATEGY = "exponential_jitter"
    HTTP_RATE_POLICY_DEFAULT_RESPECT_RETRY_AFTER = True
    HTTP_RATE_POLICY_DEFAULT_RESPECT_RESET_HEADERS = True
    HTTP_RATE_POLICY_DEFAULT_ALLOW_NON_IDEMPOTENT_RETRY = False

    # Per-service overrides (empty by default)
    HTTP_RATE_POLICY_PER_SERVICE = {}

    # Heuristics weighting defaults (used by analysis.compute_final_score)
    HEURISTICS_WEIGHTS_DEFAULT = {
        "base_score": 0.30,
        "repo_version_match": 0.30,
        "repo_stars": 0.15,
        "repo_contributors": 0.10,
        "repo_last_activity": 0.10,
        "repo_present_in_registry": 0.05,
    }
    # Runtime copy that may be overridden via YAML configuration
    HEURISTICS_WEIGHTS = dict(HEURISTICS_WEIGHTS_DEFAULT)


# ----------------------------
# YAML configuration overrides
# ----------------------------

def _first_existing(paths: list[str]) -> Optional[str]:
    """Return first existing file path from list or None."""
    for p in paths:
        if p and os.path.isfile(os.path.expanduser(p)):
            return os.path.expanduser(p)
    return None


def _candidate_config_paths() -> list[str]:
    """Compute candidate config paths in priority order."""
    paths: list[str] = []
    # Highest priority: explicit env override
    env_path = os.environ.get("DEPGATE_CONFIG")
    if env_path:
        paths.append(env_path)

    # Current directory
    paths.extend(
        [
            "./depgate.yml",
            "./.depgate.yml",
        ]
    )

    # XDG base (Linux/Unix)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        paths.append(os.path.join(xdg, "depgate", "depgate.yml"))
    else:
        paths.append(
            os.path.join(
                os.path.expanduser("~"),
                ".config",
                "depgate",
                "depgate.yml",
            )
        )

    # macOS Application Support
    if platform.system().lower() == "darwin":
        paths.append(
            os.path.join(
                os.path.expanduser("~"),
                "Library",
                "Application Support",
                "depgate",
                "depgate.yml",
            )
        )

    # Windows APPDATA
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            paths.append(os.path.join(appdata, "depgate", "depgate.yml"))

    return paths


def _load_yaml_config() -> Dict[str, Any]:
    """Load YAML config from first existing candidate path; returns {} when not found or YAML unavailable."""
    if yaml is None:  # PyYAML not installed
        return {}
    cfg_path = _first_existing(_candidate_config_paths())
    if not cfg_path:
        return {}
    try:
        with open(cfg_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh) or {}
            if isinstance(data, dict):
                return data
            return {}
    except Exception:  # pylint: disable=broad-exception-caught
        return {}


def _apply_config_overrides(cfg: Dict[str, Any]) -> None:  # pylint: disable=too-many-locals, too-many-branches, too-many-statements
    """Apply selected overrides from YAML config onto Constants."""
    http = cfg.get("http", {}) or {}
    registry = cfg.get("registry", {}) or {}
    provider = cfg.get("provider", {}) or {}
    rtd = cfg.get("rtd", {}) or {}

    # HTTP settings
    try:
        Constants.REQUEST_TIMEOUT = int(  # type: ignore[attr-defined]
            http.get("request_timeout", Constants.REQUEST_TIMEOUT)
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.HTTP_RETRY_MAX = int(  # type: ignore[attr-defined]
            http.get("retry_max", Constants.HTTP_RETRY_MAX)
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.HTTP_RETRY_BASE_DELAY_SEC = float(  # type: ignore[attr-defined]
            http.get("retry_base_delay_sec", Constants.HTTP_RETRY_BASE_DELAY_SEC)
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.HTTP_CACHE_TTL_SEC = int(  # type: ignore[attr-defined]
            http.get("cache_ttl_sec", Constants.HTTP_CACHE_TTL_SEC)
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    # Registry URLs
    Constants.REGISTRY_URL_PYPI = registry.get(  # type: ignore[attr-defined]
        "pypi_base_url", Constants.REGISTRY_URL_PYPI
    )
    Constants.REGISTRY_URL_NPM = registry.get(  # type: ignore[attr-defined]
        "npm_base_url", Constants.REGISTRY_URL_NPM
    )
    Constants.REGISTRY_URL_NPM_STATS = registry.get(  # type: ignore[attr-defined]
        "npm_stats_url", Constants.REGISTRY_URL_NPM_STATS
    )
    Constants.REGISTRY_URL_MAVEN = registry.get(  # type: ignore[attr-defined]
        "maven_search_url", Constants.REGISTRY_URL_MAVEN
    )

    # Provider URLs and paging
    Constants.GITHUB_API_BASE = provider.get(  # type: ignore[attr-defined]
        "github_api_base", Constants.GITHUB_API_BASE
    )
    Constants.GITLAB_API_BASE = provider.get(  # type: ignore[attr-defined]
        "gitlab_api_base", Constants.GITLAB_API_BASE
    )
    try:
        Constants.REPO_API_PER_PAGE = int(  # type: ignore[attr-defined]
            provider.get("per_page", Constants.REPO_API_PER_PAGE)
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    # Heuristics weights (optional)
    heuristics = cfg.get("heuristics", {}) or {}
    weights_cfg = heuristics.get("weights", {}) or {}
    if isinstance(weights_cfg, dict):
        merged = dict(Constants.HEURISTICS_WEIGHTS_DEFAULT)  # type: ignore[attr-defined]
        for key, default_val in Constants.HEURISTICS_WEIGHTS_DEFAULT.items():  # type: ignore[attr-defined]
            try:
                if key in weights_cfg:
                    val = float(weights_cfg.get(key, default_val))
                    if val >= 0.0:
                        merged[key] = val
            except Exception:  # pylint: disable=broad-exception-caught
                # ignore invalid entries; keep default
                pass
        Constants.HEURISTICS_WEIGHTS = merged  # type: ignore[attr-defined]

    # HTTP rate policy configuration
    rate_policy_cfg = http.get("rate_policy", {}) or {}
    default_cfg = rate_policy_cfg.get("default", {}) or {}
    per_service_cfg = rate_policy_cfg.get("per_service", {}) or {}

    # Apply default policy overrides
    try:
        Constants.HTTP_RATE_POLICY_DEFAULT_MAX_RETRIES = int(  # type: ignore[attr-defined]
            default_cfg.get(
                "max_retries",
                Constants.HTTP_RATE_POLICY_DEFAULT_MAX_RETRIES,
            )
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.HTTP_RATE_POLICY_DEFAULT_INITIAL_BACKOFF_SEC = float(  # type: ignore[attr-defined]
            default_cfg.get(
                "initial_backoff_sec",
                Constants.HTTP_RATE_POLICY_DEFAULT_INITIAL_BACKOFF_SEC,
            )
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.HTTP_RATE_POLICY_DEFAULT_MULTIPLIER = float(  # type: ignore[attr-defined]
            default_cfg.get(
                "multiplier",
                Constants.HTTP_RATE_POLICY_DEFAULT_MULTIPLIER,
            )
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.HTTP_RATE_POLICY_DEFAULT_JITTER_PCT = float(  # type: ignore[attr-defined]
            default_cfg.get(
                "jitter_pct",
                Constants.HTTP_RATE_POLICY_DEFAULT_JITTER_PCT,
            )
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.HTTP_RATE_POLICY_DEFAULT_MAX_BACKOFF_SEC = float(  # type: ignore[attr-defined]
            default_cfg.get(
                "max_backoff_sec",
                Constants.HTTP_RATE_POLICY_DEFAULT_MAX_BACKOFF_SEC,
            )
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.HTTP_RATE_POLICY_DEFAULT_TOTAL_RETRY_TIME_CAP_SEC = float(  # type: ignore[attr-defined]
            default_cfg.get(
                "total_retry_time_cap_sec",
                Constants.HTTP_RATE_POLICY_DEFAULT_TOTAL_RETRY_TIME_CAP_SEC,
            )
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.HTTP_RATE_POLICY_DEFAULT_STRATEGY = str(  # type: ignore[attr-defined]
            default_cfg.get(
                "strategy",
                Constants.HTTP_RATE_POLICY_DEFAULT_STRATEGY,
            )
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.HTTP_RATE_POLICY_DEFAULT_RESPECT_RETRY_AFTER = bool(  # type: ignore[attr-defined]
            default_cfg.get(
                "respect_retry_after",
                Constants.HTTP_RATE_POLICY_DEFAULT_RESPECT_RETRY_AFTER,
            )
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.HTTP_RATE_POLICY_DEFAULT_RESPECT_RESET_HEADERS = bool(  # type: ignore[attr-defined]
            default_cfg.get(
                "respect_reset_headers",
                Constants.HTTP_RATE_POLICY_DEFAULT_RESPECT_RESET_HEADERS,
            )
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.HTTP_RATE_POLICY_DEFAULT_ALLOW_NON_IDEMPOTENT_RETRY = bool(  # type: ignore[attr-defined]
            default_cfg.get(
                "allow_non_idempotent_retry",
                Constants.HTTP_RATE_POLICY_DEFAULT_ALLOW_NON_IDEMPOTENT_RETRY,
            )
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    # Apply per-service overrides
    if isinstance(per_service_cfg, dict):
        merged_per_service: Dict[str, Any] = {}
        for host, service_config in per_service_cfg.items():
            if isinstance(service_config, dict):
                merged_per_service[host] = service_config
        Constants.HTTP_RATE_POLICY_PER_SERVICE = merged_per_service  # type: ignore[attr-defined]

    # deps.dev configuration
    depsdev = cfg.get("depsdev", {}) or {}
    try:
        Constants.DEPSDEV_ENABLED = bool(  # type: ignore[attr-defined]
            depsdev.get("enabled", Constants.DEPSDEV_ENABLED)
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        base = depsdev.get("base_url", Constants.DEPSDEV_BASE_URL)
        if isinstance(base, str) and base.strip():
            Constants.DEPSDEV_BASE_URL = base  # type: ignore[attr-defined]
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.DEPSDEV_CACHE_TTL_SEC = int(  # type: ignore[attr-defined]
            depsdev.get("cache_ttl_sec", Constants.DEPSDEV_CACHE_TTL_SEC)
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.DEPSDEV_MAX_CONCURRENCY = int(  # type: ignore[attr-defined]
            depsdev.get("max_concurrency", Constants.DEPSDEV_MAX_CONCURRENCY)
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.DEPSDEV_MAX_RESPONSE_BYTES = int(  # type: ignore[attr-defined]
            depsdev.get("max_response_bytes", Constants.DEPSDEV_MAX_RESPONSE_BYTES)
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.DEPSDEV_STRICT_OVERRIDE = bool(  # type: ignore[attr-defined]
            depsdev.get("strict_override", Constants.DEPSDEV_STRICT_OVERRIDE)
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    # RTD
    Constants.READTHEDOCS_API_BASE = rtd.get(  # type: ignore[attr-defined]
        "api_base", Constants.READTHEDOCS_API_BASE
    )


def _parse_bool_env(value: str) -> Optional[bool]:
    """Parse common boolean-like environment variable values."""
    s = str(value).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    return None


def _apply_env_overrides() -> None:
    """Apply environment variable overrides for deps.dev integration."""
    # Precedence model: env overrides YAML/defaults; CLI overrides env in main()
    enabled = os.environ.get("DEPGATE_DEPSDEV_ENABLED")
    if enabled is not None:
        parsed = _parse_bool_env(enabled)
        if parsed is not None:
            Constants.DEPSDEV_ENABLED = parsed  # type: ignore[attr-defined]

    base = os.environ.get("DEPGATE_DEPSDEV_BASE_URL")
    if base:
        Constants.DEPSDEV_BASE_URL = base  # type: ignore[attr-defined]

    ttl = os.environ.get("DEPGATE_DEPSDEV_CACHE_TTL_SEC")
    if ttl:
        try:
            Constants.DEPSDEV_CACHE_TTL_SEC = int(ttl)  # type: ignore[attr-defined]
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    conc = os.environ.get("DEPGATE_DEPSDEV_MAX_CONCURRENCY")
    if conc:
        try:
            Constants.DEPSDEV_MAX_CONCURRENCY = int(conc)  # type: ignore[attr-defined]
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    max_bytes = os.environ.get("DEPGATE_DEPSDEV_MAX_RESPONSE_BYTES")
    if max_bytes:
        try:
            Constants.DEPSDEV_MAX_RESPONSE_BYTES = int(max_bytes)  # type: ignore[attr-defined]
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    strict = os.environ.get("DEPGATE_DEPSDEV_STRICT_OVERRIDE")
    if strict is not None:
        parsed = _parse_bool_env(strict)
        if parsed is not None:
            Constants.DEPSDEV_STRICT_OVERRIDE = parsed  # type: ignore[attr-defined]


# Attempt to load and apply YAML configuration on import (no-op if unavailable)
try:
    _cfg = _load_yaml_config()
    if _cfg:
        _apply_config_overrides(_cfg)
    # Apply environment overrides regardless of YAML presence
    try:
        _apply_env_overrides()
    except Exception:  # pylint: disable=broad-exception-caught
        pass
except Exception:  # pylint: disable=broad-exception-caught
    # Never fail import due to config issues
    pass
