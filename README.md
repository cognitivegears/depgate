# DepGate — Dependency Supply‑Chain Risk & Confusion Checker

DepGate is a modular CLI that detects dependency confusion and related supply‑chain risks across npm, Maven, and PyPI projects. It analyzes dependencies from manifests, checks public registries, and flags potential risks with a simple, scriptable interface.

DepGate is a fork of Apiiro’s “Dependency Combobulator”, maintained going forward by cognitivegears. See Credits & Attribution below.

## Features

- Pluggable analysis: compare vs. heuristics levels (`compare/comp`, `heuristics/heur`).
- Multiple ecosystems: npm (`package.json`), Maven (`pom.xml`), PyPI (`requirements.txt`).
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
