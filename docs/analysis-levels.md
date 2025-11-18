# Analysis Levels

DepGate provides multiple analysis levels, each offering different depth of dependency risk assessment. This document explains each level and when to use them.

## Overview

DepGate supports four analysis levels:

- **compare** (or `comp`) - Basic presence and metadata checks
- **heuristics** (or `heur`) - Adds scoring and risk signals
- **policy** (or `pol`) - Declarative rule-based evaluation
- **linked** - Repository linkage verification

## Compare (`compare` or `comp`)

The most basic analysis level, `compare` performs presence and metadata checks against public registries.

### What it does:
- Checks if packages exist in public registries
- Retrieves basic metadata (version count, creation timestamp)
- Performs minimal risk assessment

### When to use:
- Quick checks for package existence
- Basic dependency confusion detection
- CI/CD pipelines needing fast feedback
- Initial dependency audits

### Example:
```bash
depgate scan -t npm -p left-pad -a compare -o results.json
```

## Heuristics (`heuristics` or `heur`)

Adds scoring, version count, and age-based risk signals to the compare baseline.

### What it does:
- All compare checks, plus:
- Calculates heuristic risk scores (0.0 to 1.0)
- Analyzes version count (flags packages with too few versions)
- Checks package age (flags very new packages)
- Evaluates repository metrics (stars, contributors, activity)
- Performs repository version matching

### Scoring:
- **Score = 0.0**: High risk (malicious packages, missing packages, or critical issues)
- **Score < 0.6**: Low score warning
- **Score ≥ 0.6**: Generally acceptable

### Risk Indicators:
- Missing from registry
- Low heuristic score
- Insufficient version history
- Very new package (potential typosquatting)
- Repository version mismatch

### When to use:
- Comprehensive dependency risk assessment
- Pre-deployment checks
- Security audits
- When you need detailed risk scoring

### Example:
```bash
depgate scan -t npm -p left-pad -a heur -o results.json
```

## Policy (`policy` or `pol`)

Declarative rule-based evaluation with allow/deny decisions based on configurable policies.

### What it does:
- All heuristics checks (automatically triggered if needed)
- Evaluates packages against declarative policy rules
- Makes allow/deny decisions
- Checks license compliance
- Applies regex-based inclusion/exclusion rules
- Validates metric constraints (stars, score, version count)

### Policy Configuration:
Policies are defined in YAML configuration files. See [Policy Configuration](policy-configuration.md) for detailed schema.

### When to use:
- Enforcing organizational dependency policies
- License compliance checking
- Automated approval/denial workflows
- CI/CD gates based on policy rules

### Example:
```bash
depgate scan -t npm -p left-pad -a policy -c policy.yml -o results.json
```

### Exit Behavior:
- Exits with code 1 if any package is denied by policy
- Exits with code 0 if all packages pass policy checks

## Linked (`linked`)

Verifies repository linkage to upstream source (GitHub/GitLab) and validates version tag/release matching.

### Supply Chain Context

Recent attacks, particularly in the npm ecosystem, have involved attackers compromising developer credentials (for example, via phishing) and publishing malicious versions of popular libraries. Linked analysis helps mitigate this risk by verifying that each analyzed package:

- Has a resolvable upstream source repository (GitHub/GitLab)
- Contains a tag or release that exactly corresponds to the package's published version (including v‑prefix compatibility)

### What it does:
- All compare checks, plus:
- Discovers repository URLs from registry metadata
- Validates repository exists and is accessible
- Fetches repository tags and releases
- Matches package version against repository tags/releases
- Supports multiple version matching strategies

### Version Matching Strategies

DepGate attempts to match package versions against repository tags/releases using these strategies (in order):

1. **Exact** - Raw label equality
2. **Pattern** - Custom patterns (if configured)
3. **Exact-bare** - Extracted version token equality (e.g., 'v1.0.0' tag matches '1.0.0' request)
4. **v-prefix** - vX.Y.Z ↔ X.Y.Z matching
5. **Suffix-normalized** - Maven .RELEASE/.Final/.GA stripped

### Output Fields

When `-a linked` is used, JSON output includes:
- `repositoryUrl` - Discovered repository URL
- `tagMatch` - Matching tag name (if found)
- `releaseMatch` - Matching release name (if found)
- `linked` - Boolean indicating successful linkage

### Exit Behavior:
- **Exit code 0**: All packages are linked (repository resolved + exists and version tag/release match)
- **Exit code 1**: One or more packages failed linkage checks

### When to use:
- High-security environments
- Supply chain security audits
- Pre-deployment verification
- Validating package authenticity

### Examples:

```bash
# npm
depgate scan -t npm -p left-pad -a linked -o out.json

# PyPI
depgate scan -t pypi -p requests -a linked -o out.json

# Maven
depgate scan -t maven -p org.apache.commons:commons-lang3 -a linked -o out.json

# NuGet
depgate scan -t nuget -p Newtonsoft.Json -a linked -o out.json
```

### Notes:

- **Exact-unsatisfiable guard**: When an exact spec cannot be resolved to a concrete version (e.g., CLI requested exact but no resolved_version), matching is disabled (empty version passed to matcher). Metrics still populate and provenance is recorded.

- **Repository discovery**: DepGate discovers repositories from registry metadata. See [Repository Discovery](repository-discovery.md) for details on discovery sources per ecosystem.

## Choosing the Right Analysis Level

| Use Case | Recommended Level |
|----------|------------------|
| Quick existence check | `compare` |
| General risk assessment | `heuristics` |
| Policy enforcement | `policy` |
| Supply chain verification | `linked` |
| CI/CD with custom rules | `policy` |
| Security audit | `heuristics` or `linked` |

## Combining Analysis Levels

You can run multiple analysis levels sequentially:

```bash
# First, get heuristics scores
depgate scan -t npm -d ./project -a heur -o heuristics.json

# Then, apply policy rules
depgate scan -t npm -d ./project -a policy -c policy.yml -o policy.json

# Finally, verify repository linkage
depgate scan -t npm -d ./project -a linked -o linked.json
```

## See Also

- [Repository Discovery](repository-discovery.md) - How DepGate discovers repositories
- [Policy Configuration](policy-configuration.md) - Configuring policy rules
- [Output Formats](output-formats.md) - Understanding output schemas

[← Back to README](../README.md)
