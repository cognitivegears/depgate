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
    NUGET = "nuget"


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
    REGISTRY_URL_NUGET_V3 = "https://api.nuget.org/v3/index.json"
    REGISTRY_URL_NUGET_V2 = "https://www.nuget.org/api/v2/"
    SUPPORTED_PACKAGES = [
        PackageManagers.NPM.value,
        PackageManagers.PYPI.value,
        PackageManagers.MAVEN.value,
        PackageManagers.NUGET.value,
    ]
    LEVELS = ["compare", "comp", "heuristics", "heur", "policy", "pol", "linked"]
    REQUIREMENTS_FILE = "requirements.txt"
    PACKAGE_JSON_FILE = "package.json"
    POM_XML_FILE = "pom.xml"
    PYPROJECT_TOML_FILE = "pyproject.toml"
    CSPROJ_FILE = "*.csproj"
    PACKAGES_CONFIG_FILE = "packages.config"
    PROJECT_JSON_FILE = "project.json"
    UV_LOCK_FILE = "uv.lock"
    POETRY_LOCK_FILE = "poetry.lock"
    PACKAGE_LOCK_FILE = "package-lock.json"
    YARN_LOCK_FILE = "yarn.lock"
    BUN_LOCK_FILE = "bun.lock"
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

    # Dependency scanning defaults
    DIRECT_ONLY: bool = False
    REQUIRE_LOCKFILE: bool = False

    # deps.dev integration defaults
    DEPSDEV_ENABLED: bool = True
    DEPSDEV_BASE_URL = "https://api.deps.dev/v3"
    DEPSDEV_MAX_CONCURRENCY = 4
    DEPSDEV_CACHE_TTL_SEC = 86400
    DEPSDEV_MAX_RESPONSE_BYTES = 1048576
    DEPSDEV_STRICT_OVERRIDE: bool = False

    # OpenSourceMalware integration defaults
    OSM_ENABLED: bool = False
    OSM_API_BASE_URL = "https://api.opensourcemalware.com/functions/v1"
    OSM_API_TOKEN: Optional[str] = None
    OSM_CACHE_TTL_SEC = 3600
    OSM_REQUEST_TIMEOUT = 30
    OSM_AUTH_METHOD = "header"  # "header" or "query"
    OSM_MAX_RETRIES = 5
    OSM_RATE_LIMIT_RETRY_DELAY_SEC = 1.0

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

    # Heuristics threshold defaults
    HEURISTICS_MIN_VERSIONS = DefaultHeuristics.MIN_VERSIONS.value
    HEURISTICS_MIN_RELEASE_AGE_DAYS = DefaultHeuristics.NEW_DAYS_THRESHOLD.value
    HEURISTICS_SCORE_THRESHOLD = DefaultHeuristics.SCORE_THRESHOLD.value
    HEURISTICS_RISKY_THRESHOLD = DefaultHeuristics.RISKY_THRESHOLD.value
    HEURISTICS_SCORE_DECREASE_THRESHOLD = 0.0

    # Heuristics weighting defaults (used by analysis.compute_final_score).
    # Values are relative priorities and are re-normalized at runtime to sum
    # to 1.0 across available (non-None) metrics, so absolute values here do
    # not need to sum to 1.0.
    HEURISTICS_WEIGHTS_DEFAULT = {
        "base_score": 0.30,
        "repo_version_match": 0.30,
        "repo_stars": 0.15,
        "repo_contributors": 0.10,
        "repo_last_activity": 0.10,
        "repo_present_in_registry": 0.05,
        "supply_chain_trust_score": 0.20,
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
    Constants.REGISTRY_URL_NUGET_V3 = registry.get(  # type: ignore[attr-defined]
        "nuget_v3_base_url", Constants.REGISTRY_URL_NUGET_V3
    )
    Constants.REGISTRY_URL_NUGET_V2 = registry.get(  # type: ignore[attr-defined]
        "nuget_v2_base_url", Constants.REGISTRY_URL_NUGET_V2
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

    # Heuristics thresholds
    try:
        Constants.HEURISTICS_MIN_VERSIONS = int(  # type: ignore[attr-defined]
            heuristics.get("min_versions", Constants.HEURISTICS_MIN_VERSIONS)
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.HEURISTICS_MIN_RELEASE_AGE_DAYS = max(  # type: ignore[attr-defined]
            0,
            int(
                heuristics.get(
                    "min_release_age_days",
                    Constants.HEURISTICS_MIN_RELEASE_AGE_DAYS,
                )
            ),
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.HEURISTICS_SCORE_THRESHOLD = float(  # type: ignore[attr-defined]
            heuristics.get("score_threshold", Constants.HEURISTICS_SCORE_THRESHOLD)
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.HEURISTICS_RISKY_THRESHOLD = float(  # type: ignore[attr-defined]
            heuristics.get("risky_threshold", Constants.HEURISTICS_RISKY_THRESHOLD)
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.HEURISTICS_SCORE_DECREASE_THRESHOLD = abs(  # type: ignore[attr-defined]
            float(
                heuristics.get(
                    "score_decrease_threshold",
                    Constants.HEURISTICS_SCORE_DECREASE_THRESHOLD,
                )
            )
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass

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
        # Start with existing per-service config (may include OSM defaults)
        existing = getattr(Constants, "HTTP_RATE_POLICY_PER_SERVICE", {})  # type: ignore[attr-defined]
        if isinstance(existing, dict):
            merged_per_service.update(existing)
        # Apply YAML overrides
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

    # OpenSourceMalware configuration
    osm = cfg.get("opensourcemalware", {}) or {}
    try:
        Constants.OSM_ENABLED = bool(  # type: ignore[attr-defined]
            osm.get("enabled", Constants.OSM_ENABLED)
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        base = osm.get("base_url", Constants.OSM_API_BASE_URL)
        if isinstance(base, str) and base.strip():
            Constants.OSM_API_BASE_URL = base  # type: ignore[attr-defined]
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        token = osm.get("api_token")
        if isinstance(token, str) and token.strip():
            Constants.OSM_API_TOKEN = token.strip()  # type: ignore[attr-defined]
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.OSM_CACHE_TTL_SEC = int(  # type: ignore[attr-defined]
            osm.get("cache_ttl_sec", Constants.OSM_CACHE_TTL_SEC)
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        auth_method = osm.get("auth_method", Constants.OSM_AUTH_METHOD)
        if isinstance(auth_method, str) and auth_method.lower() in ("header", "query"):
            Constants.OSM_AUTH_METHOD = auth_method.lower()  # type: ignore[attr-defined]
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.OSM_MAX_RETRIES = int(  # type: ignore[attr-defined]
            osm.get("max_retries", Constants.OSM_MAX_RETRIES)
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.OSM_RATE_LIMIT_RETRY_DELAY_SEC = float(  # type: ignore[attr-defined]
            osm.get("rate_limit_retry_delay_sec", Constants.OSM_RATE_LIMIT_RETRY_DELAY_SEC)
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    # Dependency scanning options
    scan_opts = cfg.get("scan", {}) or {}
    try:
        Constants.DIRECT_ONLY = bool(  # type: ignore[attr-defined]
            scan_opts.get("direct_only", False)
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    try:
        Constants.REQUIRE_LOCKFILE = bool(  # type: ignore[attr-defined]
            scan_opts.get("require_lockfile", False)
        )
    except Exception:  # pylint: disable=broad-exception-caught
        pass


def _parse_bool_env(value: str) -> Optional[bool]:
    """Parse common boolean-like environment variable values."""
    s = str(value).strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    return None


def _apply_env_overrides() -> None:
    """Apply environment variable overrides for deps.dev and OpenSourceMalware integration."""
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

    # OpenSourceMalware environment overrides
    osm_enabled = os.environ.get("DEPGATE_OSM_ENABLED")
    if osm_enabled is not None:
        parsed = _parse_bool_env(osm_enabled)
        if parsed is not None:
            Constants.OSM_ENABLED = parsed  # type: ignore[attr-defined]

    osm_base = os.environ.get("DEPGATE_OSM_BASE_URL")
    if osm_base:
        Constants.OSM_API_BASE_URL = osm_base  # type: ignore[attr-defined]

    osm_token = os.environ.get("DEPGATE_OSM_API_TOKEN")
    if osm_token:
        Constants.OSM_API_TOKEN = osm_token  # type: ignore[attr-defined]

    osm_ttl = os.environ.get("DEPGATE_OSM_CACHE_TTL_SEC")
    if osm_ttl:
        try:
            Constants.OSM_CACHE_TTL_SEC = int(osm_ttl)  # type: ignore[attr-defined]
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    osm_auth = os.environ.get("DEPGATE_OSM_AUTH_METHOD")
    if osm_auth and osm_auth.lower() in ("header", "query"):
        Constants.OSM_AUTH_METHOD = osm_auth.lower()  # type: ignore[attr-defined]

    osm_max_retries = os.environ.get("DEPGATE_OSM_MAX_RETRIES")
    if osm_max_retries:
        try:
            Constants.OSM_MAX_RETRIES = int(osm_max_retries)  # type: ignore[attr-defined]
        except Exception:  # pylint: disable=broad-exception-caught
            pass


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
    # Apply default OpenSourceMalware rate limit configuration if not already set
    # (applies even if no YAML config is loaded)
    if hasattr(Constants, "HTTP_RATE_POLICY_PER_SERVICE") and isinstance(
        getattr(Constants, "HTTP_RATE_POLICY_PER_SERVICE", None), dict
    ):
        if "api.opensourcemalware.com" not in Constants.HTTP_RATE_POLICY_PER_SERVICE:  # type: ignore[attr-defined]
            Constants.HTTP_RATE_POLICY_PER_SERVICE["api.opensourcemalware.com"] = {  # type: ignore[attr-defined]
                "max_retries": 5,
                "initial_backoff_sec": 1.0,
                "multiplier": 1.5,
                "max_backoff_sec": 60.0,
                "respect_retry_after": True,
                "strategy": "exponential_jitter",
            }
    else:
        # Initialize if it doesn't exist or is not a dict
        Constants.HTTP_RATE_POLICY_PER_SERVICE = {  # type: ignore[attr-defined]
            "api.opensourcemalware.com": {
                "max_retries": 5,
                "initial_backoff_sec": 1.0,
                "multiplier": 1.5,
                "max_backoff_sec": 60.0,
                "respect_retry_after": True,
                "strategy": "exponential_jitter",
            }
        }
except Exception:  # pylint: disable=broad-exception-caught
    # Never fail import due to config issues
    pass
