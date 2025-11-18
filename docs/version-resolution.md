# Version Resolution

DepGate provides ecosystem-aware version resolution with strict prerelease policies. This document explains how version resolution works for each supported package manager.

## Overview

Version resolution converts package specifications (ranges, versions, etc.) into concrete versions. Each ecosystem has specific semantics:

- **npm**: Semantic versioning (semver)
- **PyPI**: PEP 440
- **Maven**: Maven versioning with SNAPSHOT handling
- **NuGet**: Semantic versioning (SemVer 2.0)

## Rightmost-Colon Token Parsing

For Maven coordinates, DepGate uses rightmost-colon token parsing to extract `groupId:artifactId`:

**Examples:**
- `org.apache.commons:commons-lang3` → groupId: `org.apache.commons`, artifactId: `commons-lang3`
- `com.example:my-package:1.0.0` → groupId: `com.example`, artifactId: `my-package`, version: `1.0.0`

For npm/PyPI/NuGet, package names are preserved as-is (no colon parsing).

## npm Resolution

### Semantic Versioning (semver)

npm uses semantic versioning with range support.

### Prerelease Handling

**Default Behavior:**
- Prereleases are **excluded** from `latest` and range resolution
- Prereleases are **excluded** unless explicitly included in the range

**Examples:**
```bash
# Latest stable version (excludes prereleases)
depgate scan -t npm -p left-pad

# Specific version
depgate scan -t npm -p left-pad:1.0.0

# Range (excludes prereleases)
depgate scan -t npm -p 'left-pad:^1.0.0'

# Include prereleases in range
depgate scan -t npm -p 'left-pad:^1.0.0-0'  # Includes prereleases
```

### Range Semantics

- `^1.0.0` - Compatible with 1.0.0 (>=1.0.0 <2.0.0)
- `~1.0.0` - Approximately 1.0.0 (>=1.0.0 <1.1.0)
- `>=1.0.0 <2.0.0` - Explicit range
- `1.0.0` - Exact version

## PyPI Resolution

### PEP 440 Compliance

PyPI uses PEP 440 versioning specification.

### Prerelease Handling

**Default Behavior:**
- Prereleases are **excluded** unless explicitly requested
- Prereleases include: alpha, beta, rc, dev, post releases

**Examples:**
```bash
# Latest stable version (excludes prereleases)
depgate scan -t pypi -p requests

# Specific version
depgate scan -t pypi -p 'requests:2.28.0'

# Range (excludes prereleases)
depgate scan -t pypi -p 'requests:>=2.28.0,<3.0.0'

# Include prereleases
depgate scan -t pypi -p 'requests:>=2.28.0a1'  # Includes alpha
```

### Version Specifiers

- `==2.28.0` - Exact version
- `>=2.28.0,<3.0.0` - Range
- `~=2.28.0` - Compatible release (>=2.28.0,<2.29.0)
- `>=2.28.0` - Minimum version

## Maven Resolution

### SNAPSHOT Exclusion

**Default Behavior:**
- `latest` excludes SNAPSHOT versions
- SNAPSHOT versions are development snapshots and excluded from stable resolution

**Examples:**
```bash
# Latest stable version (excludes SNAPSHOT)
depgate scan -t maven -p org.apache.commons:commons-lang3

# Specific version
depgate scan -t maven -p 'org.apache.commons:commons-lang3:3.12.0'

# SNAPSHOT (if explicitly requested)
depgate scan -t maven -p 'org.apache.commons:commons-lang3:3.13.0-SNAPSHOT'
```

### Bracket Semantics

Maven version ranges use bracket notation:

- `[1.0.0,2.0.0)` - Inclusive lower, exclusive upper
- `(1.0.0,2.0.0]` - Exclusive lower, inclusive upper
- `[1.0.0]` - Exact version
- `[1.0.0,)` - Minimum version

**Examples:**
```bash
# Range
depgate scan -t maven -p 'org.apache.commons:commons-lang3:[3.0.0,4.0.0)'
```

### Version Suffixes

Maven versions may include suffixes that are normalized during matching:
- `.RELEASE` - Release marker
- `.Final` - Final release marker
- `.GA` - General Availability marker

These suffixes are stripped during repository tag matching (see [Repository Discovery](repository-discovery.md)).

## NuGet Resolution

### Semantic Versioning (SemVer 2.0)

NuGet uses Semantic Versioning 2.0 specification.

### Prerelease Handling

**Default Behavior:**
- Prereleases are **excluded** from `latest` unless explicitly included
- Prereleases include: alpha, beta, rc, preview releases

**Examples:**
```bash
# Latest stable version (excludes prereleases)
depgate scan -t nuget -p Newtonsoft.Json

# Specific version
depgate scan -t nuget -p 'Newtonsoft.Json:13.0.1'

# Range (excludes prereleases)
depgate scan -t nuget -p 'Newtonsoft.Json:[13.0.0,14.0.0)'

# Include prereleases
depgate scan -t nuget -p 'Newtonsoft.Json:13.0.1-beta1'  # Specific prerelease
```

### Version Ranges

- `[13.0.0,14.0.0)` - Inclusive lower, exclusive upper
- `(13.0.0,14.0.0]` - Exclusive lower, inclusive upper
- `13.0.0` - Exact version
- `[13.0.0,)` - Minimum version

## Resolution Examples

### npm

```bash
# Resolve latest stable
depgate scan -t npm -p left-pad
# Resolves to: 1.0.0 (latest stable, excludes 1.0.1-beta)

# Resolve specific version
depgate scan -t npm -p 'left-pad:1.0.0'
# Resolves to: 1.0.0 (exact)

# Resolve range
depgate scan -t npm -p 'left-pad:^1.0.0'
# Resolves to: 1.0.2 (latest compatible, excludes prereleases)
```

### PyPI

```bash
# Resolve latest stable
depgate scan -t pypi -p requests
# Resolves to: 2.31.0 (latest stable, excludes 2.32.0a1)

# Resolve specific version
depgate scan -t pypi -p 'requests:2.28.0'
# Resolves to: 2.28.0 (exact)

# Resolve range
depgate scan -t pypi -p 'requests:>=2.28.0,<3.0.0'
# Resolves to: 2.31.0 (latest in range, excludes prereleases)
```

### Maven

```bash
# Resolve latest stable
depgate scan -t maven -p org.apache.commons:commons-lang3
# Resolves to: 3.12.0 (latest stable, excludes 3.13.0-SNAPSHOT)

# Resolve specific version
depgate scan -t maven -p 'org.apache.commons:commons-lang3:3.12.0'
# Resolves to: 3.12.0 (exact)

# Resolve range
depgate scan -t maven -p 'org.apache.commons:commons-lang3:[3.0.0,4.0.0)'
# Resolves to: 3.12.0 (latest in range, excludes SNAPSHOT)
```

### NuGet

```bash
# Resolve latest stable
depgate scan -t nuget -p Newtonsoft.Json
# Resolves to: 13.0.3 (latest stable, excludes 13.1.0-beta1)

# Resolve specific version
depgate scan -t nuget -p 'Newtonsoft.Json:13.0.1'
# Resolves to: 13.0.1 (exact)

# Resolve range
depgate scan -t nuget -p 'Newtonsoft.Json:[13.0.0,14.0.0)'
# Resolves to: 13.0.3 (latest in range, excludes prereleases)
```

## Resolution Failures

When version resolution fails:

1. **Package not found**: Package doesn't exist in registry
2. **Version not found**: Specified version doesn't exist
3. **Range unsatisfiable**: No versions match the range
4. **Network error**: Cannot reach registry

**Error Handling:**
- Resolution failures are logged
- Analysis continues with available information
- Missing versions are flagged in risk assessment

## Version Format Details

### npm (semver)

- Format: `MAJOR.MINOR.PATCH[-PRERELEASE][+BUILD]`
- Examples: `1.0.0`, `1.0.0-beta.1`, `1.0.0+20130313144700`

### PyPI (PEP 440)

- Format: `[N!]N(.N)*[{a|b|rc}N][.postN][.devN]`
- Examples: `1.0.0`, `1.0.0a1`, `1.0.0.post1`, `1.0.0.dev1`

### Maven

- Format: `MAJOR.MINOR.PATCH[-QUALIFIER]`
- Examples: `1.0.0`, `1.0.0-SNAPSHOT`, `1.0.0.RELEASE`, `1.0.0.Final`

### NuGet (SemVer 2.0)

- Format: `MAJOR.MINOR.PATCH[-PRERELEASE][+METADATA]`
- Examples: `1.0.0`, `1.0.0-beta.1`, `1.0.0+metadata`

## See Also

- [Supported Package Managers](supported-package-managers.md) - Package format details
- [Repository Discovery](repository-discovery.md) - Version matching in repositories
- [Analysis Levels](analysis-levels.md) - How resolution affects analysis

[← Back to README](../README.md)
