# DepGate — Dependency Supply‑Chain Risk & Confusion Checker

DepGate is a modular CLI that detects dependency confusion and related supply‑chain risks across npm, Maven, PyPI, and NuGet projects. It analyzes dependencies from manifests, checks public registries, and flags potential risks with a simple, scriptable interface.

DepGate is a fork of Apiiro's "Dependency Combobulator", maintained going forward by cognitivegears. See [Credits & Attribution](#credits--attribution) below.

## Features

- **Multiple ecosystems**: npm, PyPI, Maven, NuGet
- **Pluggable analysis**: compare, heuristics, policy, and linked levels
- **Supply-chain trust signals**: provenance/signature detection, trust score, and trust regressions
- **Release-age guardrails**: configurable minimum release age to reduce zero-day exposure
- **Policy presets for supply chain**: built-in deny rules for trust regressions and too-new releases
- **Repository verification**: Discovers and validates upstream source repositories
- **OpenSourceMalware integration**: Optional malicious package detection
- **Registry proxy server**: Drop-in registry replacement with policy enforcement
- **Flexible inputs**: Single package, manifest scan, or list from file
- **Structured outputs**: Human-readable logs plus CSV/JSON exports for CI
- **Designed for automation**: Predictable exit codes and quiet/log options

## Quick Start

**Option 1: Run without installation** (using uvx):

```bash
# Single package (npm)
uvx depgate scan -t npm -p left-pad

# Scan a project directory (Maven)
uvx depgate scan -t maven -d ./my-project

# Heuristics analysis with JSON output
uvx depgate scan -t pypi -a heur -o results.json
```

**Option 2: Install first** (using pipx or pip):

```bash
# Install
pipx install depgate
# or: pip install depgate

# Then use depgate directly
depgate scan -t npm -p left-pad
depgate scan -t maven -d ./my-project
depgate scan -t pypi -a heur -o results.json
```

## Installation

### Requirements

- Python 3.10+
- Network access for registry lookups (when running analysis)
- OpenSourceMalware API token (optional, for malicious package detection)

### Install

**Using uv (development):**

```bash
uv venv && source .venv/bin/activate
uv sync
```

**From PyPI:**

```bash
# Install globally
pip install depgate

# Install in isolated environment
pipx install depgate

# Run without installation (requires uv)
uvx depgate --help
```

**Note**: After installation via `pip` or `pipx`, you can use `depgate` directly. Without installation, use `uvx depgate`.

## Basic Usage

### Input Methods

- **Single package** (`-p, --package`): Analyze one package

  ```bash
  depgate scan -t npm -p left-pad
  depgate scan -t maven -p org.apache.commons:commons-lang3
  ```

- **Directory scan** (`-d, --directory`): Scan project for dependencies

  ```bash
  depgate scan -t npm -d ./my-project
  depgate scan -t pypi -d ./my-project
  ```

- **File list** (`-l, --load_list`): Analyze packages from a file

  ```bash
  depgate scan -t npm -l packages.txt
  ```

See [Supported Package Managers](https://github.com/cognitivegears/depgate/blob/main/docs/supported-package-managers.md) for format details and examples.

### Analysis Levels

- **`compare`** (or `comp`): Basic presence and metadata checks
- **`heuristics`** (or `heur`): Adds scoring and risk signals
- **`policy`** (or `pol`): Declarative rule-based evaluation
- **`linked`**: Repository linkage verification

See [Analysis Levels](https://github.com/cognitivegears/depgate/blob/main/docs/analysis-levels.md) for detailed explanations.

## Supported Package Managers

| Package Manager | Language | Manifest Files |
|----------------|----------|---------------|
| **npm** | JavaScript/TypeScript | `package.json` |
| **PyPI** | Python | `requirements.txt`, `pyproject.toml` |
| **Maven** | Java/Kotlin/Scala | `pom.xml` |
| **NuGet** | .NET/C# | `.csproj`, `packages.config`, `project.json` |

See [Supported Package Managers](https://github.com/cognitivegears/depgate/blob/main/docs/supported-package-managers.md) for complete details, lock file support, package formats, and examples.

## Major Modes

### CLI Scan Mode (Primary)

The primary mode for dependency analysis:

```bash
depgate scan -t <ecosystem> -p <package> -a <level> -o <output>
```

### MCP Server Mode (Experimental)

DepGate includes an MCP server that exposes analysis capabilities via three tools:

- `Lookup_Latest_Version` - Resolve latest stable versions
- `Scan_Project` - Analyze project dependencies
- `Scan_Dependency` - Analyze single dependencies

See [MCP Server](https://github.com/cognitivegears/depgate/blob/main/docs/mcp-server.md) for setup, tools, and client examples.

### Proxy Server Mode

DepGate can act as a registry proxy, intercepting package manager requests and evaluating packages against policies:

```bash
# Start proxy server with policy enforcement
depgate proxy --port 8080 --config policy.yml

# Increase max request body size (bytes) for publishes/uploads
depgate proxy --port 8080 --config policy.yml --client-max-size 52428800

# Configure npm to use proxy
npm config set registry http://localhost:8080

# All npm install commands are now evaluated
npm install lodash  # Allowed or blocked based on policy
```

The proxy supports three decision modes:
- **block**: Return 403 for policy violations (default)
- **warn**: Allow but log violations
- **audit**: Allow all, log for review

See [Proxy Server](https://github.com/cognitivegears/depgate/blob/main/docs/proxy-server.md) for setup and configuration.

## Output Formats

DepGate supports multiple output formats:

- **stdout**: Human-readable logs (default)
- **JSON**: Structured data for programmatic use
- **CSV**: Tabular format for spreadsheets

```bash
depgate scan -t npm -p left-pad -a heur -o results.json
depgate scan -t npm -p left-pad -a heur -o results.csv
```

See [Output Formats](https://github.com/cognitivegears/depgate/blob/main/docs/output-formats.md) for complete schema and field descriptions.

## Configuration

DepGate supports configuration via YAML files, environment variables, and CLI arguments. Configuration can customize:

- Registry URLs
- HTTP behavior
- Heuristics weights
- Policy rules
- OpenSourceMalware settings

See [Configuration](https://github.com/cognitivegears/depgate/blob/main/docs/configuration.md) for details and examples.

## Additional Features

### OpenSourceMalware Integration

Optional malicious package detection via OpenSourceMalware.com API:

```bash
DEPGATE_OSM_API_TOKEN=token depgate scan -t npm -p package-name -a heur
```

See [OpenSourceMalware Integration](https://github.com/cognitivegears/depgate/blob/main/docs/opensourcemalware.md) for setup and usage.

### Policy Rules

Declarative rule-based evaluation with allow/deny decisions:

```bash
depgate scan -t npm -d ./project -a policy -c policy.yml
```

See [Policy Configuration](https://github.com/cognitivegears/depgate/blob/main/docs/policy-configuration.md) for schema and examples.

### Supply-Chain Trust & Release-Age Controls

Trust and provenance signals are evaluated per release and compared to the previous release when available. This enables:

- provenance/signature presence checks
- trust-score decrease detection
- provenance/signature regression detection
- minimum release-age policy gates

```bash
# Built-in preset: deny trust regressions and releases newer than configured minimum age
depgate scan -t npm -d ./project -a policy --policy-preset supply-chain --policy-min-release-age-days 7

# Strict mode: also deny when trust signals are missing
depgate scan -t pypi -d ./project -a policy --policy-preset supply-chain-strict --policy-min-release-age-days 7
```

### Repository Discovery

Automatic discovery and validation of upstream source repositories:

```bash
depgate scan -t npm -p left-pad -a linked
```

See [Repository Discovery](https://github.com/cognitivegears/depgate/blob/main/docs/repository-discovery.md) for discovery sources and version matching.

### Version Resolution

Ecosystem-aware version resolution with strict prerelease policies. See [Version Resolution](https://github.com/cognitivegears/depgate/blob/main/docs/version-resolution.md) for details per ecosystem.

## CLI Options

### Main Options

- `-t, --type {npm,pypi,maven,nuget}`: Package manager
- `-p/‑d/‑l`: Input source (mutually exclusive)
- `-a, --analysis {compare,comp,heuristics,heur,policy,pol,linked}`: Analysis level
- `-o, --output <path>`: Output file path
- `-f, --format {json,csv}`: Output format (auto-detected from extension)
- `-c, --config <path>`: Configuration file (YAML/JSON/YML)
- `--set KEY=VALUE`: Override configuration values
- `--policy-preset {default,supply-chain,supply-chain-strict}`: Built-in policy preset selection
- `--policy-min-release-age-days <N>`: Minimum release age used by built-in policy presets
- `--loglevel {DEBUG,INFO,WARNING,ERROR,CRITICAL}`: Logging level
- `--logfile <path>`: Log to file
- `-q, --quiet`: Suppress stdout output
- `-r, --recursive`: Recursively scan directories
- `--error-on-warnings`: Exit with non-zero code if risks detected

### OpenSourceMalware Options

- `--osm-disable`: Disable OpenSourceMalware checks
- `--osm-api-token <token>`: API token
- `--osm-token-command <cmd>`: Command to retrieve token
- `--osm-base-url <url>`: Override API URL
- `--osm-cache-ttl <seconds>`: Cache TTL
- `--osm-auth-method {header,query}`: Authentication method
- `--osm-max-retries <count>`: Maximum retries

Run `depgate scan --help` for complete option list.

## Exit Codes

- `0`: Success (no risks or informational only)
- `1`: File/IO error (or policy denial, or linked analysis failure)
- `2`: Connection error
- `3`: Risks found and `--error-on-warnings` set

**Note**: For `-a linked`, exits with `0` only when all packages are linked; otherwise `1`.

## Documentation

### Detailed Guides

- [Supported Package Managers](https://github.com/cognitivegears/depgate/blob/main/docs/supported-package-managers.md) - Complete package manager reference
- [Analysis Levels](https://github.com/cognitivegears/depgate/blob/main/docs/analysis-levels.md) - Understanding analysis types
- [Configuration](https://github.com/cognitivegears/depgate/blob/main/docs/configuration.md) - YAML config and environment variables
- [Policy Configuration](https://github.com/cognitivegears/depgate/blob/main/docs/policy-configuration.md) - Policy rules and schema
- [OpenSourceMalware](https://github.com/cognitivegears/depgate/blob/main/docs/opensourcemalware.md) - Malicious package detection
- [Repository Discovery](https://github.com/cognitivegears/depgate/blob/main/docs/repository-discovery.md) - Repository discovery and version matching
- [Version Resolution](https://github.com/cognitivegears/depgate/blob/main/docs/version-resolution.md) - Ecosystem-specific resolution semantics
- [MCP Server](https://github.com/cognitivegears/depgate/blob/main/docs/mcp-server.md) - MCP server setup and tools
- [Proxy Server](https://github.com/cognitivegears/depgate/blob/main/docs/proxy-server.md) - Registry proxy for policy enforcement
- [Output Formats](https://github.com/cognitivegears/depgate/blob/main/docs/output-formats.md) - CSV and JSON schemas

## Contributing

See `AGENTS.md` for repository layout, development commands, and linting guidelines.

**Lint:**

```bash
uv run pylint src
```

## Credits & Attribution

DepGate is a fork of "Dependency Combobulator" originally developed by Apiiro and its contributors: <https://github.com/apiiro/combobulator> - see `CONTRIBUTORS.md`.

Licensed under the Apache License 2.0. See `LICENSE` and `NOTICE`.
