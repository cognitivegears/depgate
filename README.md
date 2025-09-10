# DepGate — Dependency Supply‑Chain Risk & Confusion Checker

DepGate is a modular CLI that detects dependency confusion and related supply‑chain risks across npm, Maven, and PyPI projects. It analyzes dependencies from manifests, checks public registries, and flags potential risks with a simple, scriptable interface.

DepGate is a fork of Apiiro’s “Dependency Combobulator”, maintained going forward by cognitivegears. See Credits & Attribution below.

## Features

- Pluggable analysis: compare vs. heuristics levels (`compare/comp`, `heuristics/heur`).
- Multiple ecosystems: npm (`package.json`), Maven (`pom.xml`), PyPI (`requirements.txt`).
- Cross‑ecosystem version resolution with strict prerelease policies (npm/PyPI exclude prereleases by default; Maven latest excludes SNAPSHOT).
- Repository discovery and version validation (GitHub/GitLab): provenance, metrics (stars, last activity, contributors), and version match strategies (exact, pattern, exact‑bare, v‑prefix, suffix‑normalized).
- Flexible inputs: single package, manifest scan, or list from file.
- Structured outputs: human‑readable logs plus CSV/JSON exports for CI.
- Designed for automation: predictable exit codes and quiet/log options.

## Requirements

- Python 3.8+
- Network access for registry lookups when running analysis

## Install

Using uv (development):

- `uv venv && source .venv/bin/activate`
- `uv sync`

From PyPI (after publishing):

- pip: `pip install depgate`
- pipx: `pipx install depgate`
- uvx: `uvx depgate --help`

## Quick Start

- Single package (npm): `depgate -t npm -p left-pad`
- Scan a repo (Maven): `depgate -t maven -d ./tests`
- Heuristics + JSON: `depgate -t pypi -a heur -j out.json`

With uv during development:

- `uv run depgate -t npm -d ./tests`
- `uv run depgate -t pypi -a heur -j out.json`

## Inputs and Scanning

- `-p, --package <name>`: single package name
  - npm: package name (e.g., `left-pad`)
  - PyPI: project name (e.g., `requests`)
  - Maven: not used (see below)
- `-d, --directory <path>`: scan local source
  - npm: finds `package.json` (and `devDependencies`)
  - Maven: finds `pom.xml`, emits `groupId:artifactId`
  - PyPI: finds `requirements.txt`
- `-l, --load_list <file>`: newline‑delimited identifiers
  - npm/PyPI: package names per line
  - Maven: `groupId:artifactId` per line

## Analysis Levels

- `compare` or `comp`: presence/metadata checks against public registries
- `heuristics` or `heur`: adds scoring, version count, age signals

## Repository discovery & version validation

DepGate discovers canonical source repositories from registry metadata, normalizes URLs, fetches metrics, and attempts to match the published version against repository releases/tags.

- Discovery sources:
  - npm: versions[dist‑tags.latest].repository (string or object), fallbacks to homepage and bugs.url
  - PyPI: info.project_urls (Repository/Source/Code preferred), fallback Homepage/Documentation; Read the Docs URLs are resolved to backing repos
  - Maven: POM <scm> (url/connection/developerConnection) with parent traversal; fallback <url> when repo‑like
- URL normalization: canonical https://host/owner/repo (strip .git), host detection (github|gitlab), monorepo directory hints preserved in provenance
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

See detailed design in [docs/repository-integration.md](docs/repository-integration.md:1) and architecture in [docs/provider-architecture.md](docs/provider-architecture.md:1).

## Output

- Default: logs to stdout (respecting `--loglevel` and `--quiet`)
- CSV: `-c, --csv <path>`
  - Columns: `Package Name, Package Type, Exists on External, Org/Group ID, Score, Version Count, Timestamp, Risk: Missing, Risk: Low Score, Risk: Min Versions, Risk: Too New, Risk: Any Risks`
- JSON: `-j, --json <path)`
  - Array of objects with keys: `packageName, orgId, packageType, exists, score, versionCount, createdTimestamp, risk.{hasRisk,isMissing,hasLowScore,minVersions,isNew}`

## CLI Options (summary)

- `-t, --type {npm,pypi,maven}`: package manager
- `-p/‑d/‑l`: input source (mutually exclusive)
- `-a, --analysis {compare,comp,heuristics,heur}`: analysis level
- `-c/‑j`: CSV/JSON export paths
- Logging: `--loglevel {DEBUG,INFO,WARNING,ERROR,CRITICAL}`, `--logfile <path>`, `-q, --quiet`
- Scanning: `-r, --recursive` (for `--directory` scans)
- CI: `--error-on-warnings` (non‑zero exit if risks detected)

## Resolution semantics (overview)

- Rightmost‑colon token parsing for Maven coordinates (groupId:artifactId) while preserving ecosystem normalization for npm/PyPI names.
- Ecosystem‑aware resolution:
  - npm: ranges respect semver; prereleases excluded from latest/ranges unless explicitly included
  - PyPI: PEP 440; prereleases excluded unless explicitly requested
  - Maven: latest excludes SNAPSHOT; ranges honor bracket semantics

## YAML configuration

DepGate optionally reads a YAML configuration file to override defaults such as registry URLs and HTTP behavior.

Search order (first found wins):
1) DEPGATE_CONFIG environment variable (absolute path)
2) ./depgate.yml (or ./.depgate.yml)
3) $XDG_CONFIG_HOME/depgate/depgate.yml (or ~/.config/depgate/depgate.yml)
4) macOS: ~/Library/Application Support/depgate/depgate.yml
5) Windows: %APPDATA%\\depgate\\depgate.yml

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

## Exit Codes

- `0`: success (no risks or informational only)
- `1`: file/IO error
- `2`: connection error
- `3`: risks found and `--error-on-warnings` set

## Contributing

- See `AGENTS.md` for repo layout, dev commands, and linting.
- Lint: `uv run pylint src`

## Credits & Attribution

- DepGate is a fork of “Dependency Combobulator” originally developed by Apiiro and its contributors: https://github.com/apiiro/combobulator - see `CONTRIBUTORS.md`.
- Licensed under the Apache License 2.0. See `LICENSE` and `NOTICE`.
