# Output Formats

DepGate supports multiple output formats for analysis results. This document describes the structure and fields for each format.

## Output Options

### Default: stdout

By default, DepGate logs results to stdout (respecting `--loglevel` and `--quiet` flags).

### File Export

Use `-o, --output <path>` to export results to a file:

```bash
depgate scan -t npm -p left-pad -o results.json
depgate scan -t npm -p left-pad -o results.csv
```

### Format Selection

The format is inferred from the file extension:
- `.json` → JSON format
- `.csv` → CSV format

Or specify explicitly with `-f, --format`:

```bash
depgate scan -t npm -p left-pad -o results.txt -f json
```

If `--format` is omitted and the extension is unrecognized, defaults to JSON.

## CSV Format

### Columns

CSV output includes the following columns (in order):

1. `Package Name` - Package identifier
2. `Package Type` - Ecosystem (npm, pypi, maven, nuget)
3. `Exists on External` - Boolean (true/false)
4. `Org/Group ID` - Organization or group identifier
5. `Score` - Heuristic score (0.0-1.0, if heuristics analysis)
6. `Version Count` - Number of published versions
7. `Timestamp` - Selected release timestamp (epoch milliseconds)
8. `Risk: Missing` - Boolean risk flag
9. `Risk: Low Score` - Boolean risk flag
10. `Risk: Min Versions` - Boolean risk flag
11. `Risk: Too New` - Boolean risk flag
12. `Risk: Score Decrease` - Trust score decrease risk flag
13. `Risk: Provenance Regression` - Provenance regressed risk flag
14. `Risk: Registry Signature Regression` - Signature regressed risk flag
15. `Risk: Any Risks` - Boolean (true if any risk is present)
16. `requested_spec` - Original requested version/range
17. `resolved_version` - Selected resolved version
18. `resolution_mode` - Version resolution mode
19. `dependency_relation` - Dependency relation metadata
20. `dependency_requirement` - Dependency requirement metadata
21. `dependency_scope` - Dependency scope metadata
22. `release_age_days` - Age of selected release in days
23. `supply_chain_trust_score` - Current trust score (0.0-1.0)
24. `supply_chain_previous_trust_score` - Previous release trust score
25. `supply_chain_trust_score_delta` - Current minus previous trust score
26. `provenance_present` - Current release provenance signal
27. `previous_provenance_present` - Previous release provenance signal
28. `provenance_regressed` - True when provenance dropped
29. `registry_signature_present` - Current release signature signal
30. `previous_registry_signature_present` - Previous release signature signal
31. `registry_signature_regressed` - True when signature dropped
32. `checksums_present` - Current release checksum evidence (ecosystem-dependent)
33. `previous_checksums_present` - Previous release checksum evidence
34. `previous_release_version` - Previous version used for regression comparison
35. `repo_stars` - Repository stars
36. `repo_contributors` - Repository contributors
37. `repo_last_activity` - Repository last activity timestamp
38. `repo_present_in_registry` - Registry metadata includes repository signal
39. `repo_version_match` - Selected release matches repo tag/release

### Example

```csv
Package Name,Package Type,Exists on External,Org/Group ID,Score,Version Count,Timestamp,Risk: Missing,Risk: Low Score,Risk: Min Versions,Risk: Too New,Risk: Score Decrease,Risk: Provenance Regression,Risk: Registry Signature Regression,Risk: Any Risks,requested_spec,resolved_version,resolution_mode,dependency_relation,dependency_requirement,dependency_scope,release_age_days,supply_chain_trust_score,supply_chain_previous_trust_score,supply_chain_trust_score_delta,provenance_present,previous_provenance_present,provenance_regressed,registry_signature_present,previous_registry_signature_present,registry_signature_regressed,checksums_present,previous_checksums_present,previous_release_version,repo_stars,repo_contributors,repo_last_activity,repo_present_in_registry,repo_version_match
left-pad,npm,true,,0.85,5,1458582003923,false,false,false,false,false,false,false,false,^1.3.0,1.3.0,range,,,,3600,1.0,1.0,0.0,true,true,false,true,true,false,,,1.2.0,1000,42,2026-01-10T12:00:00Z,true,true
```

## JSON Format

### Schema

JSON output is an array of package objects. Each object contains:

#### Core Fields

- `packageName` (string) - Package identifier
- `packageType` (string) - Ecosystem: "npm", "pypi", "maven", "nuget"
- `orgId` (string|null) - Organization or group identifier
- `exists` (boolean) - Whether package exists in registry
- `versionCount` (integer) - Number of published versions
- `createdTimestamp` (integer|null) - Selected release timestamp (epoch milliseconds)
- `release_age_days` (integer|null) - Selected release age in days
- `supply_chain_trust_score` (float|null) - Trust score from available provenance/signature signals
- `supply_chain_previous_trust_score` (float|null) - Previous release trust score
- `supply_chain_trust_score_delta` (float|null) - Current minus previous trust score
- `supply_chain_trust_score_decreased` (boolean|null) - True when trust score decreased vs previous release
- `provenance_present` (boolean|null) - Current release provenance signal
- `previous_provenance_present` (boolean|null) - Previous release provenance signal
- `provenance_regressed` (boolean|null) - True when provenance existed previously but not currently
- `registry_signature_present` (boolean|null) - Current release signature signal
- `previous_registry_signature_present` (boolean|null) - Previous release signature signal
- `registry_signature_regressed` (boolean|null) - True when signature existed previously but not currently
- `checksums_present` (boolean|null) - Current release checksum evidence (ecosystem-dependent)
- `previous_checksums_present` (boolean|null) - Previous release checksum evidence
- `previous_release_version` (string|null) - Previous version used for regression comparison

#### Risk Fields (heuristics analysis)

- `score` (float) - Heuristic score (0.0-1.0)
- `risk.hasRisk` (boolean) - True if any risk is present
- `risk.isMissing` (boolean) - Package not found in registry
- `risk.hasLowScore` (boolean) - Score below threshold (< 0.6)
- `risk.minVersions` (boolean) - Insufficient version history
- `risk.isNew` (boolean) - Release is newer than minimum release-age threshold
- `risk.scoreDecreased` (boolean|null) - Trust score decrease risk
- `risk.provenanceRegressed` (boolean|null) - Provenance regression risk
- `risk.registrySignatureRegressed` (boolean|null) - Signature regression risk

#### Policy Fields (policy analysis)

- `policy.decision` (string) - "allow" or "deny"
- `policy.violated_rules` (array) - List of violated rule names
- `policy.evaluated_metrics` (object) - Metric values used in evaluation

#### License Fields (license checking enabled)

- `license.id` (string|null) - License identifier (e.g., "MIT", "Apache-2.0")
- `license.available` (boolean) - Whether license information is available
- `license.source` (string) - Source of license info ("registry" or "repository")

#### OpenSourceMalware Fields (OSM enabled)

- `osmMalicious` (boolean) - True if package is flagged as malicious
- `osmReason` (string|null) - Reason for flagging (if malicious)
- `osmThreatCount` (integer) - Number of threats detected
- `osmSeverity` (string|null) - Severity level (if malicious)

#### Linked Analysis Fields (linked analysis)

- `repositoryUrl` (string|null) - Discovered repository URL
- `tagMatch` (boolean|null) - Whether selected release matched a repository tag
- `releaseMatch` (boolean|null) - Whether selected release matched a repository release
- `linked` (boolean) - True if repository linkage verified

### Example

```json
[
  {
    "packageName": "left-pad",
    "packageType": "npm",
    "orgId": null,
    "exists": true,
    "score": 0.85,
    "versionCount": 5,
    "createdTimestamp": 1458582003923,
    "release_age_days": 3600,
    "supply_chain_trust_score": 1.0,
    "supply_chain_previous_trust_score": 1.0,
    "supply_chain_trust_score_delta": 0.0,
    "provenance_present": true,
    "previous_provenance_present": true,
    "provenance_regressed": false,
    "registry_signature_present": true,
    "previous_registry_signature_present": true,
    "registry_signature_regressed": false,
    "previous_release_version": "1.2.0",
    "risk": {
      "hasRisk": false,
      "isMissing": false,
      "hasLowScore": false,
      "minVersions": false,
      "isNew": false,
      "scoreDecreased": false,
      "provenanceRegressed": false,
      "registrySignatureRegressed": false
    },
    "policy": {
      "decision": "allow",
      "violated_rules": [],
      "evaluated_metrics": {
        "heuristic_score": 0.85,
        "stars_count": 1000,
        "version_count": 5
      }
    },
    "license": {
      "id": "MIT",
      "available": true,
      "source": "registry"
    },
    "repositoryUrl": "https://github.com/stevemao/left-pad",
    "tagMatch": true,
    "releaseMatch": false,
    "linked": true
  }
]
```

## Field Availability

Fields are included based on:

1. **Analysis level**: Different levels produce different fields
2. **Configuration**: Some fields require specific configuration (e.g., license checking)
3. **Data availability**: Fields are only included if data is available

### By Analysis Level

#### Compare (`compare`)

- Core fields
- Basic risk fields (isMissing)

#### Heuristics (`heuristics`)

- All compare fields
- Score
- All risk fields
- Repository fields (if repository discovered)

#### Policy (`policy`)

- All heuristics fields (automatically triggered)
- Policy decision fields
- License fields (if license checking enabled)

#### Linked (`linked`)

- All compare fields
- Repository URL
- Tag/release match fields
- Linked status

## Output Examples

### Basic Scan

```bash
depgate scan -t npm -p left-pad -a compare -o results.json
```

**Output:**
```json
[
  {
    "packageName": "left-pad",
    "packageType": "npm",
    "exists": true,
    "versionCount": 5,
    "risk": {
      "isMissing": false
    }
  }
]
```

### Heuristics Scan

```bash
depgate scan -t npm -p left-pad -a heur -o results.json
```

**Output:**
```json
[
  {
    "packageName": "left-pad",
    "packageType": "npm",
    "exists": true,
    "score": 0.85,
    "versionCount": 5,
    "risk": {
      "hasRisk": false,
      "isMissing": false,
      "hasLowScore": false,
      "minVersions": false,
      "isNew": false
    }
  }
]
```

### Policy Scan

```bash
depgate scan -t npm -p left-pad -a policy -c policy.yml -o results.json
```

**Output:**
```json
[
  {
    "packageName": "left-pad",
    "packageType": "npm",
    "exists": true,
    "score": 0.85,
    "versionCount": 5,
    "risk": {
      "hasRisk": false
    },
    "policy": {
      "decision": "allow",
      "violated_rules": [],
      "evaluated_metrics": {
        "heuristic_score": 0.85,
        "version_count": 5
      }
    }
  }
]
```

### Linked Scan

```bash
depgate scan -t npm -p left-pad -a linked -o results.json
```

**Output:**
```json
[
  {
    "packageName": "left-pad",
    "packageType": "npm",
    "exists": true,
    "repositoryUrl": "https://github.com/stevemao/left-pad",
    "tagMatch": true,
    "releaseMatch": false,
    "linked": true
  }
]
```

### With OpenSourceMalware

```bash
DEPGATE_OSM_API_TOKEN=token depgate scan -t npm -p malicious-pkg -a heur -o results.json
```

**Output:**
```json
[
  {
    "packageName": "malicious-pkg",
    "packageType": "npm",
    "exists": true,
    "score": 0.0,
    "osmMalicious": true,
    "osmReason": "Known malicious package",
    "osmThreatCount": 1,
    "osmSeverity": "high",
    "risk": {
      "hasRisk": true
    }
  }
]
```

## Logging vs. Export

### Logging (stdout)

- Human-readable format
- Respects `--loglevel` and `--quiet`
- Includes progress and status messages
- Not structured for parsing

### Export (file)

- Structured format (JSON/CSV)
- Machine-readable
- Suitable for CI/CD integration
- No progress messages

### Combined Usage

You can use both:

```bash
depgate scan -t npm -p left-pad -a heur -o results.json
# Logs to stdout AND exports to results.json
```

Or suppress stdout:

```bash
depgate scan -t npm -p left-pad -a heur -o results.json -q
# Only exports to results.json, no stdout
```

## CSV Considerations

### Limitations

- Nested objects are flattened (e.g., `risk.hasRisk` becomes `Risk: Any Risks`)
- Arrays are serialized as strings
- Policy, license, and OpenSourceMalware objects are not exported in CSV

### When to Use CSV

- Spreadsheet analysis
- Simple reporting
- Quick data inspection

### When to Use JSON

- Programmatic processing
- Complex nested data
- Complete field information
- CI/CD integration

## See Also

- [Analysis Levels](analysis-levels.md) - Understanding what fields are available per level
- [Policy Configuration](policy-configuration.md) - Policy output fields
- [OpenSourceMalware](opensourcemalware.md) - OSM output fields

[← Back to README](../README.md)
