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
7. `Timestamp` - Package creation timestamp
8. `Risk: Missing` - Boolean risk flag
9. `Risk: Low Score` - Boolean risk flag
10. `Risk: Min Versions` - Boolean risk flag
11. `Risk: Too New` - Boolean risk flag
12. `Risk: Any Risks` - Boolean (true if any risk is present)
13. `[policy fields]` - Policy decision and violated rules (if policy analysis)
14. `[license fields]` - License information (if license checking enabled)
15. `[osm fields]` - OpenSourceMalware fields (if OSM enabled)

### Example

```csv
Package Name,Package Type,Exists on External,Org/Group ID,Score,Version Count,Timestamp,Risk: Missing,Risk: Low Score,Risk: Min Versions,Risk: Too New,Risk: Any Risks
left-pad,npm,true,,0.85,5,2016-03-21T17:40:03.923Z,false,false,false,false,false
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
- `createdTimestamp` (string) - ISO 8601 timestamp of package creation

#### Risk Fields (heuristics analysis)

- `score` (float) - Heuristic score (0.0-1.0)
- `risk.hasRisk` (boolean) - True if any risk is present
- `risk.isMissing` (boolean) - Package not found in registry
- `risk.hasLowScore` (boolean) - Score below threshold (< 0.6)
- `risk.minVersions` (boolean) - Insufficient version history
- `risk.isNew` (boolean) - Package is very new (potential typosquatting)

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
- `tagMatch` (string|null) - Matching tag name (if found)
- `releaseMatch` (string|null) - Matching release name (if found)
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
    "createdTimestamp": "2016-03-21T17:40:03.923Z",
    "risk": {
      "hasRisk": false,
      "isMissing": false,
      "hasLowScore": false,
      "minVersions": false,
      "isNew": false
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
    "tagMatch": "1.0.0",
    "releaseMatch": null,
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
    "tagMatch": "1.0.0",
    "releaseMatch": null,
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

- Nested objects are flattened (e.g., `risk.hasRisk` becomes `Risk: Has Risk`)
- Arrays are serialized as strings
- Some fields may be omitted for brevity

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
