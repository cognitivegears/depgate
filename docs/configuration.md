# Configuration

DepGate supports configuration via YAML files, environment variables, and CLI arguments. This document explains all configuration options and their precedence.

## Configuration Precedence

Configuration is applied in the following order (later sources override earlier ones):

1. **Built-in defaults**
2. **YAML configuration file** (if found)
3. **Environment variables**
4. **CLI arguments** (highest precedence)

## YAML Configuration File

DepGate automatically searches for configuration files in this order (first found wins):

1. `DEPGATE_CONFIG` environment variable (absolute path)
2. `./depgate.yml` (or `./.depgate.yml`)
3. `$XDG_CONFIG_HOME/depgate/depgate.yml` (or `~/.config/depgate/depgate.yml`)
4. macOS: `~/Library/Application Support/depgate/depgate.yml`
5. Windows: `%APPDATA%\\depgate\\depgate.yml`

### Full Configuration Example

```yaml
# HTTP client settings
http:
  request_timeout: 30        # seconds
  retry_max: 3
  retry_base_delay_sec: 0.3
  cache_ttl_sec: 300

# Registry URLs
registry:
  pypi_base_url: "https://pypi.org/pypi/"
  npm_base_url: "https://registry.npmjs.org/"
  npm_stats_url: "https://api.npms.io/v2/package/mget"
  maven_search_url: "https://search.maven.org/solrsearch/select"
  nuget_v3_base_url: "https://api.nuget.org/v3/index.json"
  nuget_v2_base_url: "https://www.nuget.org/api/v2/"

# Repository provider settings
provider:
  github_api_base: "https://api.github.com"
  gitlab_api_base: "https://gitlab.com/api/v4"
  per_page: 100

# Heuristics weights (relative priorities)
heuristics:
  weights:
    base_score: 0.30
    repo_version_match: 0.30
    repo_stars: 0.15
    repo_contributors: 0.10
    repo_last_activity: 0.10
    repo_present_in_registry: 0.05

# Read the Docs API
rtd:
  api_base: "https://readthedocs.org/api/v3"

# deps.dev integration
depsdev:
  enabled: true
  base_url: "https://api.deps.dev/v3"
  cache_ttl_sec: 86400
  max_concurrency: 4
  max_response_bytes: 1048576
  strict_override: false

# OpenSourceMalware integration
opensourcemalware:
  enabled: false
  base_url: "https://api.opensourcemalware.com/functions/v1"
  api_token: ""  # Set via environment variable or CLI for security
  cache_ttl_sec: 3600
  auth_method: "header"  # "header" or "query"
  max_retries: 5
  rate_limit_retry_delay_sec: 1.0

# Dependency scanning options
scan:
  direct_only: false        # Only scan direct dependencies from manifests, even when lockfiles exist
  require_lockfile: false  # Require a lockfile for package managers that support it (npm, pypi, nuget)

# HTTP rate limit and retry policy
http:
  rate_policy:
    default:
      max_retries: 0
      initial_backoff_sec: 0.5
      multiplier: 2.0
      jitter_pct: 0.2
      max_backoff_sec: 60.0
      total_retry_time_cap_sec: 120.0
      strategy: "exponential_jitter"
      respect_retry_after: true
      respect_reset_headers: true
      allow_non_idempotent_retry: false
    per_service:
      "api.opensourcemalware.com":
        max_retries: 5
        initial_backoff_sec: 1.0
        multiplier: 1.5
        max_backoff_sec: 60.0
        respect_retry_after: true
        strategy: "exponential_jitter"
```

## Configuration Sections

### HTTP Settings

```yaml
http:
  request_timeout: 30        # Timeout in seconds for all HTTP requests
  retry_max: 3               # Maximum number of retries
  retry_base_delay_sec: 0.3  # Base delay between retries (seconds)
  cache_ttl_sec: 300         # HTTP response cache TTL (seconds)
```

### Registry URLs

Override default registry URLs:

```yaml
registry:
  pypi_base_url: "https://pypi.org/pypi/"
  npm_base_url: "https://registry.npmjs.org/"
  npm_stats_url: "https://api.npms.io/v2/package/mget"
  maven_search_url: "https://search.maven.org/solrsearch/select"
  nuget_v3_base_url: "https://api.nuget.org/v3/index.json"
  nuget_v2_base_url: "https://www.nuget.org/api/v2/"
```

### Provider Settings

Configure GitHub/GitLab API access:

```yaml
provider:
  github_api_base: "https://api.github.com"
  gitlab_api_base: "https://gitlab.com/api/v4"
  per_page: 100  # Results per page for paginated API calls
```

**Note**: Set `GITHUB_TOKEN` and/or `GITLAB_TOKEN` environment variables to raise rate limits for provider API calls.

### Heuristics Weights

Configure relative priorities for heuristic scoring:

```yaml
heuristics:
  weights:
    base_score: 0.30
    repo_version_match: 0.30
    repo_stars: 0.15
    repo_contributors: 0.10
    repo_last_activity: 0.10
    repo_present_in_registry: 0.05
```

**Important**: Weights are automatically re-normalized across available metrics, so absolute values don't need to sum to 1.0. Unknown keys are ignored; missing metrics are excluded from normalization.

### deps.dev Integration

```yaml
depsdev:
  enabled: true
  base_url: "https://api.deps.dev/v3"
  cache_ttl_sec: 86400
  max_concurrency: 4
  max_response_bytes: 1048576
  strict_override: false
```

### OpenSourceMalware Integration

```yaml
opensourcemalware:
  enabled: false
  base_url: "https://api.opensourcemalware.com/functions/v1"
  api_token: ""  # Prefer environment variable or CLI for security
  cache_ttl_sec: 3600
  auth_method: "header"  # "header" or "query"
  max_retries: 5
  rate_limit_retry_delay_sec: 1.0
```

**Security Note**: Never commit API tokens in YAML files. Use environment variables or CLI arguments instead.

### Dependency Scanning Options

```yaml
scan:
  direct_only: false        # Only scan direct dependencies from manifests, even when lockfiles exist
  require_lockfile: false  # Require a lockfile for package managers that support it (npm, pypi, nuget)
```

- **`direct_only`**: When `true`, only scans direct dependencies from manifest files (package.json, pyproject.toml, requirements.txt, pom.xml, .csproj). Lockfiles are still discovered and can be used for version resolution, but transitive dependencies are not extracted. Default: `false` (scans all dependencies from lockfiles when available).

- **`require_lockfile`**: When `true`, requires a lockfile to be present for package managers that support it:
  - **npm**: Requires `package-lock.json`, `yarn.lock`, or `bun.lock`
  - **pypi**: Requires `uv.lock` or `poetry.lock` (only for pyproject.toml, not requirements.txt)
  - **nuget**: Requires `packages.lock.json`
  - **maven**: Ignored (Maven has no standard lockfile format)

  Default: `false` (lockfile is optional).

## Environment Variables

### deps.dev

- `DEPGATE_DEPSDEV_ENABLED` - Enable/disable (true/false, 1/0, yes/no)
- `DEPGATE_DEPSDEV_BASE_URL` - Override base URL
- `DEPGATE_DEPSDEV_CACHE_TTL_SEC` - Cache TTL in seconds
- `DEPGATE_DEPSDEV_MAX_CONCURRENCY` - Max concurrent requests
- `DEPGATE_DEPSDEV_MAX_RESPONSE_BYTES` - Max response size
- `DEPGATE_DEPSDEV_STRICT_OVERRIDE` - Strict override mode (true/false)

### OpenSourceMalware

- `DEPGATE_OSM_ENABLED` - Enable/disable (true/false, 1/0, yes/no)
- `DEPGATE_OSM_API_TOKEN` - API token
- `DEPGATE_OSM_BASE_URL` - Override base URL
- `DEPGATE_OSM_CACHE_TTL_SEC` - Cache TTL in seconds
- `DEPGATE_OSM_AUTH_METHOD` - "header" or "query"
- `DEPGATE_OSM_MAX_RETRIES` - Maximum retries

### Repository Providers

- `GITHUB_TOKEN` - GitHub API token (raises rate limits)
- `GITLAB_TOKEN` - GitLab API token (raises rate limits)

### Configuration File Location

- `DEPGATE_CONFIG` - Absolute path to configuration file

## CLI Arguments

CLI arguments have the highest precedence and override all other configuration sources.

### Configuration File

```bash
depgate scan -c ./custom-config.yml -t npm -p left-pad
```

### Policy Overrides

Use `--set` to override specific configuration values:

```bash
depgate scan -t npm -p left-pad -a policy --set policy.metrics.heuristic_score.min=0.8
```

### OpenSourceMalware

```bash
depgate scan -t npm -p left-pad --osm-api-token your_token
depgate scan -t npm -p left-pad --osm-disable
depgate scan -t npm -p left-pad --osm-base-url https://custom.url
```

### deps.dev

```bash
depgate scan -t npm -p left-pad --depsdev-disable
depgate scan -t npm -p left-pad --depsdev-base-url https://custom.url
```

### Dependency Scanning Options

```bash
# Only scan direct dependencies (ignore transitive dependencies from lockfiles)
depgate scan -t npm -d ./project --direct-only

# Require a lockfile for package managers that support it
depgate scan -t npm -d ./project --require-lockfile
```

## Using Configuration

### Example: Custom Registry

Create `depgate.yml`:

```yaml
registry:
  npm_base_url: "https://custom-npm-registry.example.com/"
```

### Example: Custom Heuristics Weights

```yaml
heuristics:
  weights:
    base_score: 0.40
    repo_version_match: 0.40
    repo_stars: 0.20
```

### Example: Enable OpenSourceMalware via Environment

```bash
export DEPGATE_OSM_ENABLED=true
export DEPGATE_OSM_API_TOKEN=your_token_here
depgate scan -t npm -p left-pad -a heur
```

### Example: Override via CLI

```bash
depgate scan -t npm -p left-pad -a heur \
  --osm-api-token your_token \
  --osm-cache-ttl 7200
```

## All Keys Optional

All configuration keys are optional. Unspecified values fall back to built-in defaults. Additional options may be added over time.

## See Also

- [Policy Configuration](policy-configuration.md) - Policy-specific configuration
- [OpenSourceMalware](opensourcemalware.md) - OpenSourceMalware integration details
- [Supported Package Managers](supported-package-managers.md) - Registry URLs per ecosystem

[← Back to README](../README.md)
