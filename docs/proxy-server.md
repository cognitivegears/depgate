# Proxy Server

DepGate includes a registry proxy server mode that acts as a drop-in replacement for package registries (npm, PyPI, Maven, NuGet). Requests are intercepted, packages are evaluated against policy rules, and allowed or blocked based on the configured decision mode.

## Overview

The proxy server intercepts package manager requests before they reach the upstream registry. This enables:

- **Policy enforcement**: Block packages that violate organizational policies
- **Audit logging**: Track all package installations without blocking
- **Centralized control**: Single point of policy enforcement for all package managers

## Quickstart

### Start Proxy Server

```bash
# Basic usage (defaults to localhost:8080)
depgate proxy

# With policy configuration
depgate proxy --config policy.yml

# Custom port and decision mode
depgate proxy --port 8080 --decision-mode block --config policy.yml
```

### Configure Package Manager

Once the proxy is running, configure your package manager to use it:

**npm:**
```bash
npm config set registry http://localhost:8080
npm install lodash  # Evaluated against policy
```

**pip:**
```bash
pip config set global.index-url http://localhost:8080/simple
pip install requests  # Evaluated against policy
```

**Maven:**
Add to `settings.xml`:
```xml
<mirrors>
  <mirror>
    <id>depgate-proxy</id>
    <url>http://localhost:8080</url>
    <mirrorOf>central</mirrorOf>
  </mirror>
</mirrors>
```

**NuGet:**
```bash
nuget sources Add -Name "depgate-proxy" -Source http://localhost:8080
```

## Decision Modes

The proxy supports three decision modes for handling policy violations:

| Mode | Behavior |
|------|----------|
| `block` (default) | Return HTTP 403 for policy violations |
| `warn` | Allow request but log warnings |
| `audit` | Allow request, log violations for later review |

```bash
# Block mode (default) - violations return 403
depgate proxy --decision-mode block

# Warn mode - violations are logged but allowed
depgate proxy --decision-mode warn

# Audit mode - violations logged for review, all requests allowed
depgate proxy --decision-mode audit
```

## Policy Configuration

The proxy uses the same policy configuration format as the CLI `scan -a policy` command. See [Policy Configuration](policy-configuration.md) for full details.

### Example Policy

```yaml
policy:
  fail_fast: true
  metrics:
    heuristic_score: { min: 0.6 }
    version_count: { min: 3 }
  regex:
    exclude: ["-beta$", "-alpha$", "test-"]
  license_check:
    enabled: true
    disallowed_licenses: ["GPL-3.0-only", "AGPL-3.0-only"]
```

### Using Policy with Proxy

```bash
depgate proxy --config policy.yml --decision-mode block
```

## CLI Options

### Server Options

| Option | Default | Description |
|--------|---------|-------------|
| `--host` | `127.0.0.1` | Host address to bind |
| `--allow-external` | `false` | Allow binding to non-local addresses (required for non-loopback hosts) |
| `--port` | `8080` | Port to bind |
| `--timeout` | `30` | Upstream request timeout (seconds) |

### Upstream Registries

| Option | Default | Description |
|--------|---------|-------------|
| `--upstream-npm` | `https://registry.npmjs.org` | Upstream NPM registry |
| `--upstream-pypi` | `https://pypi.org` | Upstream PyPI registry |
| `--upstream-maven` | `https://repo1.maven.org/maven2` | Upstream Maven registry |
| `--upstream-nuget` | `https://api.nuget.org` | Upstream NuGet registry |

### Policy Options

| Option | Default | Description |
|--------|---------|-------------|
| `-c, --config` | None | Path to policy config file |
| `--decision-mode` | `block` | How to handle violations |

### Caching

| Option | Default | Description |
|--------|---------|-------------|
| `--cache-ttl` | `3600` | Decision cache TTL (seconds) |

### Logging

| Option | Default | Description |
|--------|---------|-------------|
| `--log-level` | `INFO` | Logging level |

## URL Parsing

The proxy automatically detects the registry type and extracts package information from request URLs:

### NPM Patterns

| Pattern | Example |
|---------|---------|
| Package metadata | `/lodash`, `/@babel/core` |
| Version metadata | `/lodash/4.17.21` |
| Tarball download | `/lodash/-/lodash-4.17.21.tgz` |

### PyPI Patterns

| Pattern | Example |
|---------|---------|
| Simple API | `/simple/requests/` |
| JSON API | `/pypi/requests/json` |
| Version JSON | `/pypi/requests/2.31.0/json` |

### Maven Patterns

| Pattern | Example |
|---------|---------|
| Metadata | `/maven2/org/apache/commons/commons-lang3/maven-metadata.xml` |
| Artifact | `/maven2/org/apache/commons/commons-lang3/3.12.0/commons-lang3-3.12.0.jar` |
| POM | `/maven2/org/apache/commons/commons-lang3/3.12.0/commons-lang3-3.12.0.pom` |

### NuGet Patterns

| Pattern | Example |
|---------|---------|
| Registration | `/v3/registration5-gz-semver2/newtonsoft.json/index.json` |
| Flat container | `/v3-flatcontainer/newtonsoft.json/index.json` |

## Response Behavior

| Scenario | HTTP Status | Action |
|----------|-------------|--------|
| Policy: allow | 200 | Proxy upstream response |
| Policy: deny | 403 | Return JSON with violation details |
| Upstream error | 502 | Return error details |
| Parse error | Pass-through | Forward to upstream |

### Deny Response Format

When a package is blocked, the proxy returns:

```json
{
  "error": "Package blocked by policy",
  "package": "suspicious-package",
  "version": "1.0.0",
  "registry": "npm",
  "violated_rules": ["excluded by pattern: test-"],
  "message": "Package suspicious-package@1.0.0 is blocked by depgate policy. Violations: excluded by pattern: test-"
}
```

## Caching

The proxy includes two cache layers:

### Decision Cache

Caches policy evaluation results to avoid repeated lookups for the same package/version. Default TTL is 3600 seconds (1 hour).

```bash
depgate proxy --cache-ttl 7200  # 2 hour cache
```

### Response Cache

Caches upstream responses to reduce latency and load on upstream registries. This cache is internal and not directly configurable via CLI.

## Architecture

```
Package Manager → DepGate Proxy → Policy Engine → Upstream Registry
     (npm)      (http://localhost:8080)  (allow/deny)  (registry.npmjs.org)
```

1. Package manager sends request to proxy
2. Proxy parses URL to extract package/version
3. Policy engine evaluates package against rules
4. If allowed, request is forwarded to upstream
5. Response is returned (or 403 if blocked)

## Examples

### Block Untrusted Packages

```yaml
# policy.yml
policy:
  regex:
    include: ["^@myorg/", "^lodash$", "^express$"]  # Whitelist
```

```bash
depgate proxy --config policy.yml --decision-mode block
```

### Audit All Installations

```bash
depgate proxy --decision-mode audit --log-level INFO
```

All installations are allowed but logged for review.

### Custom Upstream Registry

```bash
depgate proxy \
  --upstream-npm https://npm.mycompany.com \
  --upstream-pypi https://pypi.mycompany.com
```

### CI/CD Integration

```bash
# Start proxy in background
depgate proxy --decision-mode block --config policy.yml &

# Configure npm
npm config set registry http://localhost:8080

# Run builds - policy violations will fail
npm ci
```

## Troubleshooting

### Proxy Won't Start

1. Check if port is already in use:
   ```bash
   lsof -i :8080
   ```

2. Try a different port:
   ```bash
   depgate proxy --port 8081
   ```

3. Enable debug logging:
   ```bash
   depgate proxy --log-level DEBUG
   ```

### Package Manager Can't Connect

1. Verify proxy is running:
   ```bash
   curl http://localhost:8080/lodash
   ```

2. Check registry configuration:
   ```bash
   npm config get registry
   pip config get global.index-url
   ```

### Packages Being Blocked Unexpectedly

1. Check policy configuration:
   ```bash
   cat policy.yml
   ```

2. Run in audit mode to see what's being evaluated:
   ```bash
   depgate proxy --decision-mode audit --log-level DEBUG
   ```

3. Test specific package with CLI:
   ```bash
   depgate scan -t npm -p package-name -a policy -c policy.yml
   ```

### Upstream Errors

1. Check upstream connectivity:
   ```bash
   curl https://registry.npmjs.org/lodash
   ```

2. Increase timeout:
   ```bash
   depgate proxy --timeout 60
   ```

## Limitations

- **No HTTPS termination**: The proxy uses HTTP. For HTTPS, use a reverse proxy (nginx, Caddy) in front.
- **Stateless**: Policy decisions are not persisted. Use external logging for audit trails.
- **Single registry per ecosystem**: Each ecosystem routes to one upstream registry.

## Security Considerations

- Run proxy on localhost or behind a firewall
- Use `--decision-mode block` for production policy enforcement
- Review and test policies before deployment
- Consider rate limiting via reverse proxy for public deployments

## See Also

- [Policy Configuration](policy-configuration.md) - Full policy rule documentation
- [Analysis Levels](analysis-levels.md) - Understanding policy analysis
- [Configuration](configuration.md) - General configuration options

[← Back to README](../README.md)
