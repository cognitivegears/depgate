# Policy Configuration

The `policy` analysis level uses declarative configuration to evaluate allow/deny rules against package facts. This document explains the policy configuration schema and how to use it.

## Overview

Policy analysis evaluates packages against configurable rules and makes allow/deny decisions. It can check:

- Metric constraints (heuristic score, stars, version count, etc.)
- Regex-based inclusion/exclusion patterns
- License compliance
- Custom rules

Policy configuration is used by both:
- **CLI scan mode**: `depgate scan -a policy -c policy.yml`
- **Proxy server mode**: `depgate proxy --config policy.yml`

See [Proxy Server](proxy-server.md) for using policies with the registry proxy.

## Policy Configuration Schema

Policy configuration can be provided via `-c, --config` (YAML/JSON/YML file) and overridden with `--set KEY=VALUE` options.

Built-in presets can be selected with:

```bash
depgate scan -t npm -d ./project -a policy --policy-preset supply-chain
depgate scan -t npm -d ./project -a policy --policy-preset supply-chain-strict --policy-min-release-age-days 7
```

### Full Example

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

## Configuration Sections

### Global Settings

```yaml
policy:
  enabled: true      # Enable/disable policy analysis (default: true)
  fail_fast: false   # Stop at first violation (default: false)
```

- **enabled**: When `false`, policy analysis is skipped entirely
- **fail_fast**: When `true`, evaluation stops at the first rule violation. When `false`, all rules are evaluated and all violations are reported.

### Metric Constraints

Define minimum/maximum values for package metrics:

```yaml
policy:
  metrics:
    stars_count: { min: 5 }           # Minimum GitHub/GitLab stars
    heuristic_score: { min: 0.6 }    # Minimum heuristic score (0.0-1.0)
    version_count: { min: 3 }        # Minimum number of published versions
    contributors_count: { min: 1 }    # Minimum number of contributors
```

**Available Metrics:**
- `heuristic_score` - Heuristic risk score (float, 0.0-1.0)
- `stars_count` - Repository stars (integer)
- `version_count` - Number of published versions (integer)
- `contributors_count` - Approximate contributor count (integer)
- `release_age_days` - Age of selected release in days (integer)
- `supply_chain_trust_score` - Trust signal score from provenance/signature data (float, 0.0-1.0)
- `supply_chain_trust_score_delta` - Current minus previous trust score (float)
- `supply_chain_trust_score_decreased` - True when trust score dropped vs previous release
- `provenance_regressed` - True when provenance existed previously but not in current release
- `registry_signature_regressed` - True when registry/package signature existed previously but not currently
- `registry` - Package registry name (string: "npm", "pypi", "maven", "nuget")
- `package_name` - Package identifier (string)

**Comparators:**
- `min` - Greater than or equal to (>=)
- `max` - Less than or equal to (<=)
- `eq` - Equal to (==)
- `ne` - Not equal to (!=)
- `in` - Value in list
- `not_in` - Value not in list

**Example:**
```yaml
metrics:
  heuristic_score: { min: 0.6 }
  stars_count: { min: 5, max: 100000 }
  registry: { in: ["npm", "pypi"] }
  package_name: { ne: "" }
```

### Regex Rules

Pattern-based inclusion/exclusion rules:

```yaml
policy:
  regex:
    include: ["^@myorg/", "^internal-"]  # Must match at least one
    exclude: ["-beta$", "-alpha$"]         # Must not match any
```

- **include**: Package name must match at least one pattern (optional)
- **exclude**: Package name must not match any pattern (optional)
- Exclusion patterns take precedence over inclusion patterns

**Example:**
```yaml
regex:
  include: ["^@acme/"]      # Only allow scoped packages from @acme
  exclude: ["-test$", "-dev$"]  # Exclude test/dev packages
```

### License Checking

License discovery and validation:

```yaml
policy:
  license_check:
    enabled: true
    disallowed_licenses: ["GPL-3.0-only", "AGPL-3.0-only"]
    allow_unknown: false
```

- **enabled**: Enable license discovery and checking
- **disallowed_licenses**: List of license identifiers to deny
- **allow_unknown**: When `false`, packages with unknown/missing licenses are denied

**License Discovery:**
License discovery uses LRU caching (default maxsize: 256) to minimize network calls. It follows a metadata-first strategy:

1. Check registry metadata for license information
2. Optionally fall back to repository file parsing (LICENSE, LICENSE.md)
3. Cache results per (repo_url, ref) combination

Set `policy.license_check.enabled=false` to disable all license-related network calls.

### Output Configuration

```yaml
policy:
  output:
    include_license_fields: true  # Include license fields in output
```

## Dot-Path Overrides

Override specific configuration values via CLI using dot-path notation:

```bash
# Override specific metric constraints
depgate scan -t npm -p left-pad -a policy --set policy.metrics.heuristic_score.min=0.8

# Disable license checking
depgate scan -t npm -p left-pad -a policy --set policy.license_check.enabled=false

# Change fail_fast behavior
depgate scan -t npm -p left-pad -a policy --set policy.fail_fast=true

# Add to disallowed licenses
depgate scan -t npm -p left-pad -a policy --set policy.license_check.disallowed_licenses=["GPL-3.0-only"]
```

## Implicit Heuristics Trigger

When policy rules reference heuristic-derived metrics (e.g., `heuristic_score`, `is_license_available`), the system automatically runs heuristics analysis for affected packages if those metrics are missing. This ensures policy evaluation has access to all required data without manual intervention.

**Example:**
If your policy checks `heuristic_score` but you run `-a policy` (not `-a heur`), DepGate will automatically run heuristics analysis first to compute the score.

## Heuristic: is_license_available

The `is_license_available` heuristic indicates whether license information is available for a package. This boolean value is computed from existing registry enrichment data and is automatically included when heuristics run.

## Exit Codes

- **Exit code 0**: All packages pass policy checks
- **Exit code 1**: One or more packages are denied by policy

## Examples

### Built-in Supply-Chain Presets

`--policy-preset supply-chain`:
- Deny when `release_age_days` is below minimum.
- Deny when trust score decreases (`supply_chain_trust_score_delta < 0`).
- Deny when `provenance_regressed` or `registry_signature_regressed` is true.
- Uses `allow_unknown=true` for these metrics (only enforced when available).

`--policy-preset supply-chain-strict`:
- Same rules as `supply-chain`.
- Uses `allow_unknown=false` (missing signals deny).

### Basic Policy

```yaml
policy:
  metrics:
    heuristic_score: { min: 0.6 }
    version_count: { min: 3 }
```

### Organizational Policy

```yaml
policy:
  fail_fast: true
  regex:
    include: ["^@myorg/"]
  metrics:
    heuristic_score: { min: 0.7 }
    stars_count: { min: 10 }
  license_check:
    enabled: true
    disallowed_licenses: ["GPL-3.0-only", "AGPL-3.0-only"]
    allow_unknown: false
```

### License-Only Policy

```yaml
policy:
  license_check:
    enabled: true
    disallowed_licenses: ["GPL-3.0-only"]
    allow_unknown: true  # Allow packages without license info
```

### Using Policy Configuration

```bash
# Load policy from YAML file
depgate scan -t npm -d ./project -a policy -c policy.yml -o results.json

# Override specific values
depgate scan -t npm -d ./project -a policy -c policy.yml \
  --set policy.metrics.heuristic_score.min=0.8 \
  --set policy.fail_fast=true

# Policy-only check (heuristics auto-triggered if needed)
depgate scan -t npm -d ./project -a policy -c policy.yml
```

## Policy Output

Policy analysis adds the following fields to JSON output:

```json
{
  "packageName": "left-pad",
  "policy": {
    "decision": "allow",  // or "deny"
    "violated_rules": [],  // List of violated rule names
    "evaluated_metrics": {
      "heuristic_score": 0.85,
      "stars_count": 100,
      "version_count": 5
    }
  }
}
```

When a package is denied:

```json
{
  "packageName": "suspicious-package",
  "policy": {
    "decision": "deny",
    "violated_rules": ["heuristic_score", "version_count"],
    "evaluated_metrics": {
      "heuristic_score": 0.3,  // Below minimum of 0.6
      "version_count": 1        // Below minimum of 3
    }
  }
}
```

## Best Practices

1. **Start Simple**: Begin with basic metric constraints, then add complexity
2. **Use fail_fast for CI**: Set `fail_fast: true` in CI/CD pipelines for faster feedback
3. **Cache License Data**: License discovery is cached; first run may be slower
4. **Test Policies**: Test policies against known good/bad packages before deploying
5. **Document Rules**: Document why each rule exists for team understanding

## See Also

- [Analysis Levels](analysis-levels.md) - Understanding policy analysis
- [Configuration](configuration.md) - General configuration options
- [Output Formats](output-formats.md) - Policy output schema
- [Proxy Server](proxy-server.md) - Using policies with registry proxy

[← Back to README](../README.md)
