# DepGate — Dependency Supply‑Chain Risk & Confusion Checker

DepGate is a modular CLI that detects dependency confusion and related supply‑chain risks across npm, Maven, PyPI, and NuGet projects. It analyzes dependencies from manifests, checks public registries, and flags potential risks with a simple, scriptable interface.

DepGate is a fork of Apiiro’s “Dependency Combobulator”, maintained going forward by cognitivegears. See Credits & Attribution below.

## Features

- Pluggable analysis: compare, heuristics, policy, and linked levels (`compare/comp`, `heuristics/heur`, `policy/pol`, `linked`).
- Multiple ecosystems: npm (`package.json`), Maven (`pom.xml`), PyPI (`requirements.txt`), NuGet (`.csproj`, `packages.config`, `project.json`).
- Cross‑ecosystem version resolution with strict prerelease policies (npm/PyPI exclude prereleases by default; Maven latest excludes SNAPSHOT; NuGet respects semantic versioning).
- Repository discovery and version validation (GitHub/GitLab): provenance, metrics (stars, last activity, contributors), and version match strategies (exact, pattern, exact‑bare, v‑prefix, suffix‑normalized).
- **OpenSourceMalware integration**: Optional malicious package detection via OpenSourceMalware.com API. Automatically flags malicious packages in heuristics (score = 0.0), available in policy rules, and included in MCP output. Requires API token (see Configuration).
- Flexible inputs: single package, manifest scan, or list from file.
- Structured outputs: human‑readable logs plus CSV/JSON exports for CI.
- Designed for automation: predictable exit codes and quiet/log options.

## MCP server (experimental, additive)

DepGate includes an MCP server mode that exposes existing analysis via three tools using the official MCP Python SDK.

Quickstart:

1. Start the server over stdio (default):

```bash
depgate mcp
```

1. Or start a local TCP endpoint for testing (non-standard transport used by this repo for convenience):

```bash
depgate mcp --host 127.0.0.1 --port 8765
```

Tools exposed:

- Lookup_Latest_Version: Resolve latest stable version for npm/pypi/maven/nuget per DepGate rules.
- Scan_Project: Equivalent to `depgate scan` on a project directory.
- Scan_Dependency: Analyze a single coordinate without changing your project.

Common client examples:

- Claude Desktop / IDEs with MCP: Add a server entry pointing to the `depgate mcp` executable (stdio). The client handles the stdio handshake automatically.
- Node/JS agents (stdio): Spawn `depgate mcp` with stdio pipes and speak JSON‑RPC 2.0. List tools via `tools/list`, then call with `tools/call`.
- Python agents: Use the official MCP client libs; connect over stdio to `depgate mcp`.

Sandboxing and environment:

- The server restricts filesystem access to a sandbox root. By default, it's the current working directory.
  - If you pass absolute paths (e.g., to Scan_Project), run `depgate mcp --project-dir "/abs/path"` with a root that contains those paths.
- When developing with this repo installed in editable mode, avoid adding `src/` to PYTHONPATH when launching the server; it may shadow the external `mcp` SDK package. For tests that need mocks, add only `tests/e2e_mocks` to PYTHONPATH.

Flags & env:

- `--project-dir`: sandbox root for file access
- Networking: `--offline`, `--no-network`, cache TTL/dir
- Runtime: `--log-level`, `--max-concurrency`, `--request-timeout`

Notes:

- This mode is additive; existing commands and exit codes are unchanged.
- Tests and local development can use mocks via `FAKE_REGISTRY=1` with `PYTHONPATH=src:tests/e2e_mocks`.

## Requirements

- Python 3.10+
- Network access for registry lookups when running analysis
- OpenSourceMalware API token (optional, for malicious package detection)

## Install

Using uv (development):

- `uv venv && source .venv/bin/activate`
- `uv sync`

From PyPI (after publishing):

- pip: `pip install depgate`
- pipx: `pipx install depgate`
- uvx: `uvx depgate --help`

## Quick Start

- Single package (npm): `depgate scan -t npm -p left-pad`
- Scan a repo (Maven): `depgate scan -t maven -d ./tests`
- Heuristics + JSON: `depgate scan -t pypi -a heur -o out.json`
- Single package (NuGet): `depgate scan -t nuget -p Newtonsoft.Json`
- Linked verification: `depgate scan -t npm -p left-pad -a linked -o out.json`
- With OpenSourceMalware (requires API token): `DEPGATE_OSM_API_TOKEN=your_token depgate scan -t npm -p package-name -a heur`

With uv during development:

- `uv run depgate scan -t npm -d ./tests`
- `uv run depgate scan -t pypi -a heur -o out.json`
- `uv run depgate scan -t nuget -d ./tests`

## Inputs and Scanning

- `-p, --package <name>`: single package name
  - npm: package name (e.g., `left-pad`)
  - PyPI: project name (e.g., `requests`)
  - Maven: `groupId:artifactId` (e.g., `org.apache.commons:commons-lang3`)
  - NuGet: package ID (e.g., `Newtonsoft.Json`)
- `-d, --directory <path>`: scan local source
  - npm: finds `package.json` (and `devDependencies`)
  - Maven: finds `pom.xml`, emits `groupId:artifactId`
  - PyPI: finds `requirements.txt`
  - NuGet: finds `.csproj`, `packages.config`, or `project.json`
- `-l, --load_list <file>`: newline‑delimited identifiers
  - npm/PyPI/NuGet: package names per line
  - Maven: `groupId:artifactId` per line

## Analysis Levels

- `compare` or `comp`: presence/metadata checks against public registries
- `heuristics` or `heur`: adds scoring, version count, age signals
- `policy` or `pol`: declarative rule-based evaluation with allow/deny decisions
- `linked`: mirrors compare baseline and verifies repository linkage to an upstream source (GitHub/GitLab) and a tag or release matching the package version (including v‑prefix). Exits with code 0 only when all packages pass linkage; otherwise 1.

### Linked analysis (repository linkage verification)

Supply‑chain context: recent attacks, particularly in the npm ecosystem, have involved attackers compromising developer credentials (for example, via phishing) and publishing malicious versions of popular libraries. Linked analysis helps mitigate this risk by verifying that each analyzed package:

- Has a resolvable upstream source repository (GitHub/GitLab)
- Contains a tag or release that exactly corresponds to the package’s published version (including v‑prefix compatibility)

Behavior and outputs:

- Strict exit semantics: process exits 0 only if all packages are linked; otherwise 1
- When `-a linked` is used, JSON includes: `repositoryUrl`, `tagMatch`, `releaseMatch`, and `linked`.

Examples:

- npm: `depgate scan -t npm -p left-pad -a linked -o out.json`
- pypi: `depgate scan -t pypi -p requests -a linked -o out.json`
- maven: `depgate scan -t maven -p org.apache.commons:commons-lang3 -a linked -o out.json`
- nuget: `depgate scan -t nuget -p Newtonsoft.Json -a linked -o out.json`

## Repository discovery & version validation

DepGate discovers canonical source repositories from registry metadata, normalizes URLs, fetches metrics, and attempts to match the published version against repository releases/tags.

- Discovery sources:
  - npm: versions[dist‑tags.latest].repository (string or object), fallbacks to homepage and bugs.url
  - PyPI: info.project_urls (Repository/Source/Code preferred), fallback Homepage/Documentation; Read the Docs URLs are resolved to backing repos
  - Maven: POM scm (url/connection/developerConnection) with parent traversal; fallback url when repo‑like
  - NuGet: package metadata projectUrl and repository metadata; fallback to projectUrl when repository-like
- URL normalization: canonical host/owner/repo form (strip .git), host detection (github|gitlab), monorepo directory hints preserved in provenance
- Metrics: stars, last activity timestamp, approximate contributors
- Version matching strategies (in order):
  1) exact (raw label equality)
  2) pattern (custom patterns, run against raw labels)
  3) exact‑bare (extracted version token equality; e.g., 'v1.0.0' tag matches '1.0.0' request)
  4) v‑prefix (vX.Y.Z ↔ X.Y.Z)
  5) suffix‑normalized (e.g., Maven .RELEASE/.Final/.GA stripped)
- Tag/release name returned prefers the bare token unless both v‑prefixed and bare forms co‑exist, in which case the raw label is preserved.

Notes:

- Exact‑unsatisfiable guard: when an exact spec cannot be resolved to a concrete version (e.g., CLI requested exact but no resolved_version), matching is disabled (empty version passed to matcher). Metrics still populate and provenance is recorded.

### Configuration (optional but recommended)

- export GITHUB_TOKEN and/or GITLAB_TOKEN to raise rate limits for provider API calls.

## OpenSourceMalware Integration

DepGate includes optional integration with the OpenSourceMalware.com API for malicious package detection. This integration:

- Automatically flags malicious packages in heuristics analysis (score = 0.0)
- Supports version-specific checks (critical for accurate detection)
- Integrates with policy rules and MCP output
- Works across all ecosystems (npm, PyPI, Maven, NuGet) and analysis types

**Quick start**: Set `DEPGATE_OSM_API_TOKEN` environment variable or use `--osm-api-token` flag.

### Configuration

The integration requires an API token. Provide it via:

- **Environment variable**: `DEPGATE_OSM_API_TOKEN=your_token`
- **CLI argument**: `--osm-api-token your_token`
- **Command execution**: `--osm-token-command "cat ~/.osm_token"`
- **YAML config**: See `docs/depgate.example.yml` for options

**Priority**: CLI > Environment variable > Command execution > YAML config

### Version-Specific Checks

The integration performs version-specific checks, which is critical for accurate detection:

```bash
# Check specific vulnerable version (will be flagged)
depgate scan -t npm -p 'synckit:0.11.9' -a heur

# Check specific safe version (will not be flagged)
depgate scan -t npm -p 'synckit:0.11.11' -a heur

# Check latest version (uses resolved version, not package-level check)
depgate scan -t npm -p 'synckit' -a heur
```

When no version is specified, the integration uses the resolved/latest version (not a package-level check that might incorrectly flag safe packages).

### Policy Integration

Use malware detection in policy rules:

```yaml
policy:
  rules:
    - type: malware
      fail_on_malicious: true
```

## Output

- Default: logs to stdout (respecting `--loglevel` and `--quiet`)
- File export: `-o, --output <path>` and `-f, --format {json,csv}`
  - If `--format` is omitted, inferred from `--output` extension (`.json` / `.csv`), otherwise defaults to JSON.
  - CSV columns: `Package Name, Package Type, Exists on External, Org/Group ID, Score, Version Count, Timestamp, Risk: Missing, Risk: Low Score, Risk: Min Versions, Risk: Too New, Risk: Any Risks, [policy fields], [license fields]`
  - JSON schema: objects with keys: `packageName, orgId, packageType, exists, score, versionCount, createdTimestamp, risk.{hasRisk,isMissing,hasLowScore,minVersions,isNew}, policy.{decision,violated_rules,evaluated_metrics}, license.{id,available,source}, osmMalicious, osmReason, osmThreatCount, osmSeverity`. When `-a linked` is used, the JSON also includes: `repositoryUrl`, `tagMatch`, `releaseMatch`, and `linked`.

## CLI Options (summary)

- `-t, --type {npm,pypi,maven,nuget}`: package manager
- `-p/‑d/‑l`: input source (mutually exclusive)
- `-a, --analysis {compare,comp,heuristics,heur,policy,pol,linked}`: analysis level
- Output: `-o, --output <path>` and `-f, --format {json,csv}`
- Config: `-c, --config <path>` (YAML/JSON/YML), `--set KEY=VALUE` (dot-path overrides)
- Logging: `--loglevel {DEBUG,INFO,WARNING,ERROR,CRITICAL}`, `--logfile <path>`, `-q, --quiet`
- Scanning: `-r, --recursive` (for `--directory` scans)
- CI: `--error-on-warnings` (non‑zero exit if risks detected)
- OpenSourceMalware: `--osm-disable`, `--osm-api-token <token>`, `--osm-token-command <cmd>`, `--osm-base-url <url>`, `--osm-cache-ttl <seconds>`, `--osm-auth-method {header,query}`, `--osm-max-retries <count>`

## Resolution semantics (overview)

- Rightmost‑colon token parsing for Maven coordinates (groupId:artifactId) while preserving ecosystem normalization for npm/PyPI/NuGet names.
- Ecosystem‑aware resolution:
  - npm: ranges respect semver; prereleases excluded from latest/ranges unless explicitly included
  - PyPI: PEP 440; prereleases excluded unless explicitly requested
  - Maven: latest excludes SNAPSHOT; ranges honor bracket semantics
  - NuGet: semantic versioning (SemVer 2.0); prereleases excluded from latest unless explicitly included

## YAML configuration

DepGate optionally reads a YAML configuration file to override defaults such as registry URLs and HTTP behavior.

Search order (first found wins):

1. DEPGATE_CONFIG environment variable (absolute path)
2. ./depgate.yml (or ./.depgate.yml)
3. $XDG_CONFIG_HOME/depgate/depgate.yml (or ~/.config/depgate/depgate.yml)
4. macOS: ~/Library/Application Support/depgate/depgate.yml
5. Windows: %APPDATA%\\depgate\\depgate.yml

Example:

```yaml
http:
  request_timeout: 30        # seconds
  retry_max: 3
  retry_base_delay_sec: 0.3
  cache_ttl_sec: 300

registry:
  pypi_base_url: "https://pypi.org/pypi/"
  npm_base_url: "https://registry.npmjs.org/"
  npm_stats_url: "https://api.npms.io/v2/package/mget"
  maven_search_url: "https://search.maven.org/solrsearch/select"
  nuget_v3_base_url: "https://api.nuget.org/v3/index.json"
  nuget_v2_base_url: "https://www.nuget.org/api/v2/"

provider:
  github_api_base: "https://api.github.com"
  gitlab_api_base: "https://gitlab.com/api/v4"
  per_page: 100

heuristics:
  weights:
    base_score: 0.30
    repo_version_match: 0.30
    repo_stars: 0.15
    repo_contributors: 0.10
    repo_last_activity: 0.10
    repo_present_in_registry: 0.05

rtd:
  api_base: "https://readthedocs.org/api/v3"
```

All keys are optional; unspecified values fall back to built‑in defaults. Additional options may be added over time.

Heuristics weights are non‑negative numbers expressing relative priority for each signal. They are automatically re‑normalized across the metrics that are available for a given package, so the absolute values do not need to sum to 1. Unknown keys are ignored; missing metrics are excluded from the normalization set.

## Policy Configuration

The `policy` analysis level uses declarative configuration to evaluate allow/deny rules against package facts. Policy configuration can be provided via `-c, --config` (YAML/JSON/YML file) and overridden with `--set KEY=VALUE` options.

### Policy Configuration Schema

```yaml
policy:
  enabled: true                    # Global policy enable/disable
  fail_fast: true                  # Stop at first violation (default: false)
  metrics:                         # Declarative metric constraints
    stars_count: { min: 5 }        # Minimum stars
    heuristic_score: { min: 0.6 }  # Minimum heuristic score
    version_count: { min: 3 }      # Minimum version count
  regex:                           # Regex-based rules
    include: ["^@myorg/"]          # Must match at least one include pattern
    exclude: ["-beta$"]            # Must not match any exclude pattern
  license_check:                   # License validation
    enabled: true                  # Enable license discovery/checking
    disallowed_licenses: ["GPL-3.0-only", "AGPL-3.0-only"]
    allow_unknown: false           # Allow packages with unknown licenses
  output:
    include_license_fields: true   # Include license fields in output
```

### Dot-path Override Examples

```bash
# Override specific metric constraints
depgate scan -t npm -p left-pad -a policy --set policy.metrics.heuristic_score.min=0.8

# Disable license checking
depgate scan -t npm -p left-pad -a policy --set policy.license_check.enabled=false

# Change fail_fast behavior
depgate scan -t npm -p left-pad -a policy --set policy.fail_fast=true
```

### Implicit Heuristics Trigger

When policy rules reference heuristic-derived metrics (e.g., `heuristic_score`, `is_license_available`), the system automatically runs heuristics analysis for affected packages if those metrics are missing. This ensures policy evaluation has access to all required data without manual intervention.

### License Discovery Performance

License discovery uses LRU caching (default maxsize: 256) to minimize network calls. It follows a metadata-first strategy:

1. Check registry metadata for license information
2. Optionally fall back to repository file parsing (LICENSE, LICENSE.md)
3. Cache results per (repo_url, ref) combination

Set `policy.license_check.enabled=false` to disable all license-related network calls.

### New Heuristic: is_license_available

The `is_license_available` heuristic indicates whether license information is available for a package. This boolean value is computed from existing registry enrichment data and is automatically included when heuristics run.

## Exit Codes

- `0`: success (no risks or informational only)
- `1`: file/IO error
- `2`: connection error
- `3`: risks found and `--error-on-warnings` set

Note: For `-a linked`, the process exits with `0` only when all analyzed packages are linked (repository resolved+exists and version tag/release match); otherwise it exits with `1`.

## Contributing

- See `AGENTS.md` for repo layout, dev commands, and linting.
- Lint: `uv run pylint src`

## Credits & Attribution

- DepGate is a fork of “Dependency Combobulator” originally developed by Apiiro and its contributors: <https://github.com/apiiro/combobulator> - see `CONTRIBUTORS.md`.
- Licensed under the Apache License 2.0. See `LICENSE` and `NOTICE`.
