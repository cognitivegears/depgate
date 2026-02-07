# Run Mode

DepGate's `run` mode wraps package manager commands with automatic proxy interception. Instead of manually starting a proxy and configuring each tool, `depgate run` handles everything: it starts an ephemeral proxy on a random port, configures the package manager to route through it, runs the command, and tears everything down.

## Overview

Run mode eliminates the friction of manual proxy setup. Compare:

**Without run mode (manual proxy):**
```bash
depgate proxy --port 8080 --config policy.yml &
npm config set registry http://localhost:8080
npm install lodash
npm config delete registry
kill %1
```

**With run mode:**
```bash
depgate run --config policy.yml npm install lodash
```

The proxy starts on an ephemeral port, npm is configured via environment variables, and everything is cleaned up automatically when the command finishes.

## Quickstart

```bash
# npm
depgate run npm install lodash

# pip with policy
depgate run --config policy.yml pip install requests

# yarn in warn mode
depgate run --decision-mode warn yarn add express

# Maven
depgate run mvn clean install

# uv
depgate run uv pip install flask
```

## Supported Package Managers

| Manager | Ecosystem | Config Strategy |
|---------|-----------|-----------------|
| `npm` | NPM | `npm_config_registry` env var |
| `pnpm` | NPM | `npm_config_registry` env var |
| `yarn` | NPM | `npm_config_registry` + `YARN_NPM_REGISTRY_SERVER` env vars |
| `bun` | NPM | `npm_config_registry` env var |
| `pip` | PyPI | `PIP_INDEX_URL` + `PIP_TRUSTED_HOST` env vars |
| `pip3` | PyPI | Same as pip |
| `pipx` | PyPI | Same as pip |
| `poetry` | PyPI | `PIP_INDEX_URL` + `PIP_TRUSTED_HOST` env vars (best-effort) |
| `uv` | PyPI | `UV_INDEX_URL` + `UV_INSECURE_HOST` env vars |
| `mvn` | Maven | Temp `settings.xml` with `-s` flag |
| `gradle` | Maven | Temp `init.gradle` with `--init-script` flag |
| `gradlew` | Maven | Same as gradle |
| `dotnet` | NuGet | Temp `NuGet.Config` + `--configfile` / MSBuild property |
| `nuget` | NuGet | Temp `NuGet.Config` + `-ConfigFile` flag |

## CLI Options

```
depgate run [options] [--] <command> [args...]
```

The `--` separator is recommended when the wrapped command has flags that could conflict with depgate options, but is not required when the subcommand starts with a package manager name.

### Policy Options

| Option | Default | Description |
|--------|---------|-------------|
| `-c, --config` | None | Path to policy config file (YAML or JSON) |
| `--decision-mode` | `block` | How to handle violations: `block`, `warn`, or `audit` |

### Upstream Overrides

| Option | Default | Description |
|--------|---------|-------------|
| `--upstream-npm` | `https://registry.npmjs.org` | Upstream NPM registry |
| `--upstream-pypi` | `https://pypi.org` | Upstream PyPI registry |
| `--upstream-maven` | `https://repo1.maven.org/maven2` | Upstream Maven registry |
| `--upstream-nuget` | `https://api.nuget.org` | Upstream NuGet registry |

### Other Options

| Option | Default | Description |
|--------|---------|-------------|
| `--timeout` | `30` | Upstream request timeout (seconds) |
| `--log-level` | `INFO` | Logging level |
| `--logfile` | None | Log output to file |

## How It Works

Run mode follows this lifecycle:

```
depgate run --config policy.yml npm install lodash
       |
       v
1. Start ephemeral proxy (port=0, OS assigns free port)
       |
       v
2. Wait for proxy health check (/_depgate/health)
       |
       v
3. Build wrapper config for "npm"
   - env: npm_config_registry=http://127.0.0.1:<port>
       |
       v
4. Run: npm install lodash  (with modified environment)
   - Proxy intercepts registry requests
   - Policy evaluation happens transparently
       |
       v
5. Cleanup: stop proxy, remove temp files
       |
       v
6. Exit with npm's exit code
```

The proxy runs in a background daemon thread, so it doesn't block the main process. The subprocess inherits stdin/stdout/stderr, so interactive commands work normally.

## Exit Codes

Run mode propagates the exit code from the wrapped command. If npm returns 0, `depgate run` returns 0. If the wrapped command fails with exit code 1, `depgate run` returns 1.

Special cases:
- `2` — Invalid arguments (no command, unsupported manager)
- `1` — Proxy failed to start or health check timed out
- `130` — Interrupted by Ctrl+C (SIGINT)

## Examples

### Enforce Policy During npm Install

```bash
# policy.yml blocks packages matching test patterns
depgate run --config policy.yml npm install lodash
```

If `lodash` passes policy, npm installs it normally. If it violates policy, the proxy returns HTTP 403 and npm reports the failure.

### Audit All pip Installations

```bash
depgate run --decision-mode audit --log-level INFO pip install -r requirements.txt
```

All packages are allowed through, but every request is logged for review.

### Warn Mode with yarn

```bash
depgate run --decision-mode warn --config policy.yml yarn add express axios
```

Policy violations are logged as warnings, but packages are still installed.

### Maven with Custom Upstream

```bash
depgate run --upstream-maven https://maven.mycompany.com/maven2 mvn clean install
```

### Gradle Wrapper

```bash
depgate run --config policy.yml ./gradlew build
```

Note: Use `gradlew` (not `./gradlew`) if the wrapper is on your PATH, or use the full path. Run mode extracts the basename to determine the package manager.

### dotnet Restore

```bash
depgate run --config policy.yml dotnet restore
```

### CI/CD Integration

```bash
# In a CI pipeline - block policy violations
depgate run --decision-mode block --config policy.yml npm ci
if [ $? -ne 0 ]; then
  echo "Dependency policy violation detected"
  exit 1
fi
```

### Debug Logging

```bash
depgate run --log-level DEBUG --logfile depgate.log npm install lodash
```

## Wrapper Details

### JavaScript Managers (npm, pnpm, yarn, bun)

These managers respect environment variables for registry configuration. No temp files are created.

- **npm/pnpm/bun**: Uses `npm_config_registry` env var
- **yarn**: Sets both `npm_config_registry` (v1) and `YARN_NPM_REGISTRY_SERVER` (v2+)

### Python Managers (pip, pip3, pipx, poetry)

Uses `PIP_INDEX_URL` pointing to the proxy's `/simple` endpoint and `PIP_TRUSTED_HOST` set to `127.0.0.1` (since the proxy uses HTTP, not HTTPS).

### uv

Uses `UV_INDEX_URL` (proxy's `/simple` endpoint) and `UV_INSECURE_HOST` (`127.0.0.1`). These are separate from pip's environment variables.

### Maven (mvn)

Creates a temporary `settings.xml` with a `<mirror>` element pointing all repositories to the proxy. The file is injected via `-s <path>` before the user's arguments.

If `~/.m2/settings.xml` exists, a warning is logged since the `-s` flag overrides user settings for that invocation.

### Gradle (gradle, gradlew)

Creates a temporary `init.gradle` script that overrides all project repositories with the proxy URL (including `allowInsecureProtocol true` for HTTP). The file is injected via `--init-script <path>`.

### NuGet (dotnet, nuget)

Creates a temporary `NuGet.Config` that clears existing sources and adds the proxy as the sole package source. The file path is injected into the command:

- **dotnet**: `--configfile <path>` for restore/build/run/pack, or `--property:RestoreConfigFile=<path>` for publish/test
- **nuget**: `-ConfigFile <path>`

## Temporary Files

Maven, Gradle, and NuGet wrappers create temporary configuration files. These are:
- Created in the system temp directory with a `depgate-` prefix
- Cleaned up automatically in a `finally` block (even if the command fails)
- Removed even if the process is interrupted (best-effort)

## Limitations

- **No HTTPS**: The ephemeral proxy uses HTTP on localhost. Package managers that require HTTPS for all registries may need trusted-host configuration (handled automatically by the wrappers).
- **conda not supported**: conda uses a different channel protocol. Use `depgate proxy` directly if you need conda support with custom configuration.
- **poetry limitations**: Poetry support is best-effort via pip environment variables. It works for the install phase but may not cover all poetry operations.
- **Single invocation**: Each `depgate run` starts a fresh proxy. For long-running development sessions, consider using `depgate proxy` directly.

## See Also

- [Proxy Server](proxy-server.md) - Manual proxy setup and advanced configuration
- [Policy Configuration](policy-configuration.md) - Policy rule documentation
- [Configuration](configuration.md) - General configuration options

[<- Back to README](../README.md)
