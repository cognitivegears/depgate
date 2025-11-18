# Supported Package Managers

DepGate supports dependency analysis across multiple package managers and ecosystems. This document provides a comprehensive reference for supported formats, file types, and usage patterns.

## Package Manager Support Table

| Package Manager | Language | Manifest Files | Lock Files | Package Format | Registry URL |
|----------------|----------|---------------|------------|----------------|--------------|
| **npm** | JavaScript/TypeScript | `package.json` | `package-lock.json`, `yarn.lock` (detected but not parsed) | Package name (e.g., `left-pad`) | `https://registry.npmjs.org/` |
| **PyPI** | Python | `requirements.txt`, `pyproject.toml` | `uv.lock`, `poetry.lock` | Project name (e.g., `requests`) | `https://pypi.org/pypi/` |
| **Maven** | Java/Kotlin/Scala | `pom.xml` | N/A | `groupId:artifactId` (e.g., `org.apache.commons:commons-lang3`) | `https://search.maven.org/solrsearch/select` |
| **NuGet** | .NET/C# | `.csproj`, `packages.config`, `project.json`, `Directory.Build.props` | N/A | Package ID (e.g., `Newtonsoft.Json`) | `https://api.nuget.org/v3/index.json` (V3), `https://www.nuget.org/api/v2/` (V2) |

## File Format Detection and Precedence

### npm

- **Manifest**: `package.json` is required
- **Lock Files**: `package-lock.json` and `yarn.lock` are detected but not currently parsed for dependency extraction
- **Dependencies**: Extracted from `dependencies` and `devDependencies` fields
- **Recursive Scanning**: When `-r/--recursive` is used, scans subdirectories for multiple `package.json` files

### PyPI

- **Manifest Precedence**:
  1. `pyproject.toml` (authoritative if present)
  2. `requirements.txt` (fallback if `pyproject.toml` is missing)
- **Lock File Precedence**:
  1. If `pyproject.toml` contains `[tool.uv]` → prefer `uv.lock`
  2. Else if `pyproject.toml` contains `[tool.poetry]` → prefer `poetry.lock`
  3. If both lockfiles exist without tool section → prefer `uv.lock` (warning emitted)
- **Dependencies**: Extracted from `[project.dependencies]` in `pyproject.toml` or from `requirements.txt` lines

### Maven

- **Manifest**: `pom.xml` is required
- **Parent POMs**: Parent POMs are traversed for dependency resolution
- **Dependencies**: Extracted from `<dependencies>` section, including transitive dependencies
- **Recursive Scanning**: When `-r/--recursive` is used, scans subdirectories for multiple `pom.xml` files

### NuGet

- **Manifest Files** (all are scanned):
  - `.csproj` files (PackageReference elements)
  - `packages.config` (legacy format)
  - `project.json` (project.json format)
  - `Directory.Build.props` (MSBuild directory-level props)
- **Recursive Scanning**: Enabled by default for NuGet projects (often have multiple `.csproj` files)
- **Dependencies**: Extracted from all discovered manifest files

## Package Name Formats

### npm
- Simple package name: `left-pad`
- Scoped packages: `@org/package-name`
- Example: `depgate scan -t npm -p left-pad`

### PyPI
- Project name: `requests`
- Example: `depgate scan -t pypi -p requests`

### Maven
- Format: `groupId:artifactId`
- Example: `depgate scan -t maven -p org.apache.commons:commons-lang3`
- When using `-l/--load_list`, use `groupId:artifactId` per line

### NuGet
- Package ID: `Newtonsoft.Json`
- Example: `depgate scan -t nuget -p Newtonsoft.Json`

## Input Methods

### Single Package (`-p, --package`)

```bash
# npm
depgate scan -t npm -p left-pad

# PyPI
depgate scan -t pypi -p requests

# Maven
depgate scan -t maven -p org.apache.commons:commons-lang3

# NuGet
depgate scan -t nuget -p Newtonsoft.Json
```

### Directory Scan (`-d, --directory`)

```bash
# npm - finds package.json
depgate scan -t npm -d ./my-project

# PyPI - finds requirements.txt or pyproject.toml
depgate scan -t pypi -d ./my-project

# Maven - finds pom.xml
depgate scan -t maven -d ./my-project

# NuGet - finds .csproj, packages.config, project.json, Directory.Build.props
depgate scan -t nuget -d ./my-project
```

### File List (`-l, --load_list`)

Create a file with package identifiers (one per line):

**npm/PyPI/NuGet** (`packages.txt`):
```
left-pad
requests
Newtonsoft.Json
```

**Maven** (`maven-packages.txt`):
```
org.apache.commons:commons-lang3
com.google.guava:guava
```

```bash
# npm/PyPI/NuGet
depgate scan -t npm -l packages.txt

# Maven
depgate scan -t maven -l maven-packages.txt
```

## Version Resolution

Each ecosystem has specific version resolution semantics:

- **npm**: Respects semver; prereleases excluded from latest/ranges unless explicitly included
- **PyPI**: PEP 440 compliant; prereleases excluded unless explicitly requested
- **Maven**: Latest excludes SNAPSHOT; ranges honor bracket semantics
- **NuGet**: Semantic versioning (SemVer 2.0); prereleases excluded from latest unless explicitly included

For detailed version resolution information, see [Version Resolution](version-resolution.md).

## Examples

### Scan a Node.js project
```bash
depgate scan -t npm -d ./my-node-project -a heur -o results.json
```

### Scan a Python project with pyproject.toml
```bash
depgate scan -t pypi -d ./my-python-project -a heur -o results.json
```

### Scan a Maven project
```bash
depgate scan -t maven -d ./my-java-project -a heur -o results.json
```

### Scan a .NET project
```bash
depgate scan -t nuget -d ./my-dotnet-project -a heur -o results.json
```

### Analyze a single package
```bash
depgate scan -t npm -p left-pad -a linked -o out.json
```

### Analyze multiple packages from file
```bash
depgate scan -t npm -l packages.txt -a heur -o results.json
```

## See Also

- [Analysis Levels](analysis-levels.md) - Understanding different analysis types
- [Version Resolution](version-resolution.md) - Detailed version resolution semantics
- [Configuration](configuration.md) - Customizing registry URLs and behavior

[← Back to README](../README.md)
