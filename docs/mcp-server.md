# MCP Server

DepGate includes an MCP (Model Context Protocol) server mode that exposes existing analysis capabilities via three tools using the official MCP Python SDK. This mode is experimental and additive—existing CLI commands and exit codes remain unchanged.

## Overview

The MCP server exposes DepGate's analysis capabilities to MCP-compatible clients (e.g., Claude Desktop, custom agents). It provides programmatic access to:

- Version resolution
- Project scanning
- Single dependency analysis

## Quickstart

### Start Server (stdio - default)

```bash
depgate mcp
```

The server runs over stdio, communicating via JSON-RPC 2.0.

### Start Server (TCP - for testing)

```bash
depgate mcp --host 127.0.0.1 --port 8765
```

This starts a local TCP endpoint (non-standard transport used by this repo for convenience during development).

## Tools Exposed

### 1. Lookup_Latest_Version

Resolve latest stable version for a package per DepGate rules.

**Parameters:**
- `name` (string, required) - Package name
- `ecosystem` (string, required) - One of: "npm", "pypi", "maven", "nuget"
- `versionRange` (string, optional) - Version range specifier
- `registryUrl` (string, optional) - Override registry URL

**Returns:**
```json
{
  "version": "1.0.0",
  "ecosystem": "npm",
  "packageName": "left-pad"
}
```

### 2. Scan_Project

Equivalent to `depgate scan` on a project directory.

**Parameters:**
- `projectDir` (string, required) - Project directory path
- `ecosystem` (string, optional) - Ecosystem hint (auto-detected if not provided)
- `analysisLevel` (string, optional) - Analysis level (default: "compare")
- `includeDevDependencies` (boolean, optional) - Include dev dependencies
- `includeTransitive` (boolean, optional) - Include transitive dependencies (default: true). When `false`, only scans direct dependencies from manifests, even when lockfiles exist
- `requireLockfile` (boolean, optional) - Require a lockfile for package managers that support it (default: false). When `true`, fails if lockfile is missing:
  - **npm**: Requires `package-lock.json`, `yarn.lock`, or `bun.lock`
  - **pypi**: Requires `uv.lock` or `poetry.lock` (only for pyproject.toml, not requirements.txt)
  - **nuget**: Requires `packages.lock.json`
  - **maven**: Ignored (Maven has no standard lockfile format)
- `respectLockfiles` (boolean, optional) - Respect lock files
- `offline` (boolean, optional) - Disable network calls
- `strictProvenance` (boolean, optional) - Strict provenance checking

**Returns:**
Analysis results in the same format as CLI JSON output.

### 3. Scan_Dependency

Analyze a single dependency coordinate without changing your project.

**Parameters:**
- `name` (string, required) - Package name
- `version` (string, required) - Package version
- `ecosystem` (string, required) - One of: "npm", "pypi", "maven", "nuget"
- `registryUrl` (string, optional) - Override registry URL
- `offline` (boolean, optional) - Disable network calls

**Returns:**
Analysis results for the single dependency.

## Client Examples

### Claude Desktop / IDEs with MCP

Add a server entry pointing to the `depgate mcp` executable (stdio). The client handles the stdio handshake automatically.

**Example configuration:**
```json
{
  "mcpServers": {
    "depgate": {
      "command": "depgate",
      "args": ["mcp"]
    }
  }
}
```

### Node/JS Agents (stdio)

Spawn `depgate mcp` with stdio pipes and speak JSON-RPC 2.0:

```javascript
import { spawn } from 'child_process';

const mcp = spawn('depgate', ['mcp'], {
  stdio: ['pipe', 'pipe', 'pipe']
});

// List tools
mcp.stdin.write(JSON.stringify({
  jsonrpc: '2.0',
  id: 1,
  method: 'tools/list'
}));

// Call tool
mcp.stdin.write(JSON.stringify({
  jsonrpc: '2.0',
  id: 2,
  method: 'tools/call',
  params: {
    name: 'Lookup_Latest_Version',
    arguments: {
      name: 'left-pad',
      ecosystem: 'npm'
    }
  }
}));
```

### Python Agents

Use the official MCP client libs; connect over stdio to `depgate mcp`:

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

async with stdio_client(StdioServerParameters(
    command="depgate",
    args=["mcp"]
)) as (read, write):
    async with ClientSession(read, write) as session:
        # List tools
        tools = await session.list_tools()

        # Call tool
        result = await session.call_tool(
            "Lookup_Latest_Version",
            arguments={
                "name": "left-pad",
                "ecosystem": "npm"
            }
        )
```

## Sandboxing and Environment

### Filesystem Access

The server restricts filesystem access to a sandbox root. By default, it's the current working directory.

**Custom Sandbox:**
```bash
depgate mcp --project-dir "/abs/path"
```

If you pass absolute paths (e.g., to Scan_Project), run `depgate mcp --project-dir "/abs/path"` with a root that contains those paths.

### Development Mode

When developing with this repo installed in editable mode, avoid adding `src/` to PYTHONPATH when launching the server; it may shadow the external `mcp` SDK package.

For tests that need mocks, add only `tests/e2e_mocks` to PYTHONPATH:

```bash
PYTHONPATH=tests/e2e_mocks depgate mcp
```

## Flags & Environment Variables

### Transport

- `--host` - Host for TCP server (default: stdio)
- `--port` - Port for TCP server

### Project Scoping

- `--project-dir` - Sandbox root for file access

### Networking

- `--offline` - Disable all network calls (tools return offline errors)
- `--no-network` - Hard fail any operation requiring network access
- `--cache-dir` - Optional cache directory
- `--cache-ttl` - Default cache TTL in seconds (default: 600)

### Runtime

- `--log-level` - Set logging level (default: INFO)
- `--log-json` - Emit structured JSON logs
- `--max-concurrency` - Max concurrency for registry/provider requests
- `--request-timeout` - Request timeout in seconds

### OpenSourceMalware

- `--osm-disable` - Disable OpenSourceMalware checks
- `--osm-api-token` - OpenSourceMalware API token
- `--osm-token-command` - Command to retrieve API token
- `--osm-base-url` - Override base URL
- `--osm-cache-ttl` - Cache TTL in seconds
- `--osm-auth-method` - Authentication method (header/query)
- `--osm-max-retries` - Maximum retries

## Examples

### Resolve Latest Version

```bash
# Via MCP client
# Tool: Lookup_Latest_Version
# Arguments: { "name": "left-pad", "ecosystem": "npm" }
```

### Scan Project

```bash
# Via MCP client
# Tool: Scan_Project
# Arguments: {
#   "projectDir": "/path/to/project",
#   "ecosystem": "npm",
#   "analysisLevel": "heur",
#   "includeTransitive": false,  # Only scan direct dependencies
#   "requireLockfile": true      # Require lockfile to be present
# }
```

### Analyze Single Dependency

```bash
# Via MCP client
# Tool: Scan_Dependency
# Arguments: {
#   "name": "left-pad",
#   "version": "1.0.0",
#   "ecosystem": "npm"
# }
```

## Testing and Development

### Using Mocks

Tests and local development can use mocks via `FAKE_REGISTRY=1`:

```bash
FAKE_REGISTRY=1 PYTHONPATH=src:tests/e2e_mocks depgate mcp
```

### Debugging

Enable debug logging:

```bash
depgate mcp --log-level DEBUG
```

Or with JSON logs:

```bash
depgate mcp --log-level DEBUG --log-json
```

## Notes

- This mode is **additive**; existing commands and exit codes are unchanged
- The server runs in the foreground; use process management for production
- stdio transport is recommended for production use
- TCP transport is for development/testing only

## Troubleshooting

### Server Won't Start

1. Verify DepGate is installed:
   ```bash
   depgate --version
   ```

2. Check MCP SDK is available:
   ```bash
   python -c "import mcp"
   ```

3. Enable debug logging:
   ```bash
   depgate mcp --log-level DEBUG
   ```

### Tool Calls Fail

1. Verify tool name is correct (case-sensitive)
2. Check required parameters are provided
3. Review error messages in debug logs

### Network Errors

1. Check `--offline` flag is not set
2. Verify network connectivity
3. Check registry URLs are accessible

## See Also

- [Analysis Levels](analysis-levels.md) - Understanding analysis types
- [Configuration](configuration.md) - Server configuration options
- [Supported Package Managers](supported-package-managers.md) - Ecosystem details

[← Back to README](../README.md)
