# Repository Discovery

DepGate discovers canonical source repositories from registry metadata, normalizes URLs, fetches metrics, and attempts to match published package versions against repository releases/tags. This document explains how repository discovery works.

## Overview

Repository discovery enables DepGate to:

- Verify package authenticity by linking to source repositories
- Collect repository metrics (stars, contributors, activity)
- Match package versions against repository tags/releases
- Support linked analysis for supply chain security

## Discovery Sources

DepGate discovers repositories from registry metadata using ecosystem-specific strategies:

### npm

**Primary Sources:**
- `versions[dist-tags.latest].repository` (string or object)

**Fallbacks:**
- `homepage` (if repository-like)
- `bugs.url` (if repository-like)

**Example metadata:**
```json
{
  "repository": {
    "type": "git",
    "url": "https://github.com/user/repo.git"
  }
}
```

### PyPI

**Primary Sources:**
- `info.project_urls.Repository` (preferred)
- `info.project_urls.Source`
- `info.project_urls.Code`

**Fallbacks:**
- `info.project_urls.Homepage` (if repository-like)
- `info.project_urls.Documentation` (Read the Docs URLs are resolved to backing repos)

**Read the Docs Resolution:**
If a Read the Docs URL is found, DepGate queries the Read the Docs API to resolve it to the backing source repository.

### Maven

**Primary Sources:**
- POM `<scm><url>` element
- POM `<scm><connection>` element
- POM `<scm><developerConnection>` element

**Parent POM Traversal:**
DepGate traverses parent POMs to find SCM information when not present in the child POM.

**Fallbacks:**
- POM `<url>` element (if repository-like)

**Example POM:**
```xml
<scm>
  <url>https://github.com/user/repo</url>
  <connection>scm:git:git://github.com/user/repo.git</connection>
</scm>
```

### NuGet

**Primary Sources:**
- Package metadata `projectUrl` (if repository-like)
- Package metadata `repository` metadata

**Fallbacks:**
- `projectUrl` when repository-like

**Example metadata:**
```json
{
  "projectUrl": "https://github.com/user/repo",
  "repository": {
    "type": "git",
    "url": "https://github.com/user/repo.git"
  }
}
```

## URL Normalization

DepGate normalizes repository URLs to a canonical form:

1. **Strip `.git` suffix**: `https://github.com/user/repo.git` → `https://github.com/user/repo`
2. **Host detection**: Identifies GitHub and GitLab hosts
3. **Canonical form**: `https://github.com/owner/repo` or `https://gitlab.com/owner/repo`
4. **Monorepo hints**: Directory paths in URLs are preserved in provenance metadata

**Examples:**
- `git+https://github.com/user/repo.git` → `https://github.com/user/repo`
- `https://github.com/user/repo/tree/main/packages/pkg` → `https://github.com/user/repo` (with directory hint preserved)

## Metrics Collection

DepGate fetches the following metrics from repository APIs:

### Stars
- Number of repository stars
- Log-scaled for scoring (saturates around ~1k stars)

### Last Activity
- Timestamp of most recent commit/activity
- Tiered thresholds for scoring (recent, moderate, stale)

### Contributors
- Approximate contributor count
- Saturates around ~50 contributors for scoring

### Repository Presence
- Whether a repository-like URL exists in registry metadata
- Treated as missing when only a non-repo homepage exists

## Version Matching Strategies

DepGate attempts to match package versions against repository tags/releases using these strategies (in order):

### 1. Exact Match
Raw label equality between package version and tag/release name.

**Example:**
- Package version: `1.0.0`
- Tag: `1.0.0`
- Result: ✅ Match

### 2. Pattern Match
Custom patterns (if configured) run against raw tag/release labels.

**Example:**
- Pattern: `v{version}`
- Package version: `1.0.0`
- Tag: `v1.0.0`
- Result: ✅ Match

### 3. Exact-Bare Match
Extracted version token equality. Strips prefixes/suffixes and compares core version.

**Example:**
- Package version: `1.0.0`
- Tag: `v1.0.0`
- Extracted: `1.0.0` == `1.0.0`
- Result: ✅ Match

### 4. v-Prefix Match
Bidirectional matching between `vX.Y.Z` and `X.Y.Z` formats.

**Examples:**
- Package: `1.0.0` ↔ Tag: `v1.0.0` ✅
- Package: `v1.0.0` ↔ Tag: `1.0.0` ✅

### 5. Suffix-Normalized Match
Strips common suffixes and compares versions.

**Maven Examples:**
- Package: `1.0.0.RELEASE` ↔ Tag: `1.0.0` ✅
- Package: `1.0.0.Final` ↔ Tag: `1.0.0` ✅
- Package: `1.0.0.GA` ↔ Tag: `1.0.0` ✅

## Tag/Release Name Selection

When multiple matching tags/releases are found:

- **Preference**: Bare token (without v-prefix) is preferred
- **Exception**: If both v-prefixed and bare forms co-exist, the raw label is preserved

**Example:**
- Tags: `1.0.0`, `v1.0.0`
- Package: `1.0.0`
- Selected: `1.0.0` (bare form preferred)

## Exact-Unsatisfiable Guard

When an exact spec cannot be resolved to a concrete version (e.g., CLI requested exact but no `resolved_version`), matching is disabled (empty version passed to matcher). Metrics still populate and provenance is recorded.

**Example:**
- Requested: `package-name@^1.0.0` (range)
- Resolved: `null` (couldn't resolve)
- Action: Skip version matching, but still fetch repository metrics

## Repository Provider APIs

DepGate uses the following APIs for repository access:

### GitHub
- Base URL: `https://api.github.com` (configurable)
- Authentication: `GITHUB_TOKEN` environment variable (raises rate limits)
- Endpoints:
  - `/repos/{owner}/{repo}` - Repository info
  - `/repos/{owner}/{repo}/tags` - Tags
  - `/repos/{owner}/{repo}/releases` - Releases
  - `/repos/{owner}/{repo}/contributors` - Contributors

### GitLab
- Base URL: `https://gitlab.com/api/v4` (configurable)
- Authentication: `GITLAB_TOKEN` environment variable (raises rate limits)
- Endpoints:
  - `/projects/{id}` - Project info
  - `/projects/{id}/repository/tags` - Tags
  - `/projects/{id}/releases` - Releases
  - `/projects/{id}/repository/contributors` - Contributors

### Read the Docs
- Base URL: `https://readthedocs.org/api/v3` (configurable)
- Endpoint: `/projects/{slug}` - Resolve documentation URL to source repository

## Configuration

### Provider URLs

```yaml
provider:
  github_api_base: "https://api.github.com"
  gitlab_api_base: "https://gitlab.com/api/v4"
  per_page: 100  # Results per page for paginated API calls
```

### Authentication

Set environment variables to raise rate limits:

```bash
export GITHUB_TOKEN=your_github_token
export GITLAB_TOKEN=your_gitlab_token
```

**Note**: Tokens are not read from YAML configuration files for security.

## Examples

### Basic Discovery

```bash
# Discover repository for a package
depgate scan -t npm -p left-pad -a heur -o results.json
```

Output includes:
```json
{
  "packageName": "left-pad",
  "repositoryUrl": "https://github.com/stevemao/left-pad",
  "repo_stars": 1000,
  "repo_contributors": 5,
  "repo_last_activity": "2023-01-15T10:30:00Z"
}
```

### Linked Analysis

```bash
# Verify repository linkage and version matching
depgate scan -t npm -p left-pad -a linked -o results.json
```

Output includes:
```json
{
  "packageName": "left-pad",
  "repositoryUrl": "https://github.com/stevemao/left-pad",
  "tagMatch": "1.0.0",
  "releaseMatch": null,
  "linked": true
}
```

### Version Matching Examples

**Exact Match:**
- Package: `1.0.0`
- Tag: `1.0.0`
- Result: ✅ Matched

**v-Prefix Match:**
- Package: `1.0.0`
- Tag: `v1.0.0`
- Result: ✅ Matched

**Maven Suffix:**
- Package: `1.0.0.RELEASE`
- Tag: `1.0.0`
- Result: ✅ Matched

**No Match:**
- Package: `1.0.0`
- Tags: `2.0.0`, `3.0.0`
- Result: ❌ No match

## Troubleshooting

### Repository Not Found

1. Check if package metadata includes repository URL:
   ```bash
   depgate scan -t npm -p package-name -a compare --loglevel DEBUG
   ```

2. Verify repository URL is accessible:
   ```bash
   curl https://api.github.com/repos/owner/repo
   ```

3. Check if URL normalization is correct (debug logs show normalized URLs)

### Version Mismatch

1. Verify package version format matches repository tags
2. Check if v-prefix matching is working (debug logs)
3. Review suffix normalization for Maven packages

### Rate Limiting

1. Set `GITHUB_TOKEN` or `GITLAB_TOKEN` environment variables
2. Increase cache TTL to reduce API calls
3. Check API rate limit status in debug logs

## See Also

- [Analysis Levels](analysis-levels.md) - Linked analysis details
- [Configuration](configuration.md) - Provider API configuration
- [Version Resolution](version-resolution.md) - Version format details

[← Back to README](../README.md)
