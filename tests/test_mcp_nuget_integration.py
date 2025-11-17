"""Integration test for MCP NuGet scanning functionality."""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "src" / "depgate.py"


def _spawn_mcp_stdio(env=None):
    """Spawn MCP server in stdio mode."""
    cmd = [sys.executable, "-u", str(ENTRY), "mcp"]
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env or os.environ.copy(),
        bufsize=1,
    )
    return proc


def _rpc_envelope(method, params=None, id_=1):
    """Create a JSON-RPC 2.0 envelope."""
    return json.dumps({"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}}) + "\n"


def _send_json(proc, payload_str: str) -> None:
    """Send JSON-RPC message to MCP server."""
    assert proc.stdin is not None
    proc.stdin.write(payload_str)
    proc.stdin.flush()


def _read_json_response(proc, expected_id=None, timeout=30):
    """Read a JSON-RPC response supporting either line-delimited JSON or LSP-style Content-Length frames."""
    assert proc.stdout is not None
    end = time.time() + timeout
    buf = ""
    content_len = None
    # First, try to detect LSP-style framing
    while time.time() < end:
        line = proc.stdout.readline()
        if not line:
            break
        s = line.strip()
        if not s:
            if content_len is not None:
                # Next chunk should be JSON of content_len bytes
                payload = proc.stdout.read(content_len)
                try:
                    obj = json.loads(payload)
                    if expected_id is None or obj.get("id") == expected_id:
                        return obj
                except Exception:
                    # Invalid JSON in LSP-framed payload; continue reading
                    pass
                content_len = None
                continue
            # skip empty line
            continue
        if s.lower().startswith("content-length:"):
            try:
                content_len = int(s.split(":", 1)[1].strip())
            except Exception:
                content_len = None
            continue
        # If not framed headers, attempt to parse as a standalone JSON line
        try:
            obj = json.loads(s)
            if expected_id is None or obj.get("id") == expected_id:
                return obj
        except Exception:
            # Accumulate and try again (in case of pretty-printed JSON)
            buf += s
            try:
                obj = json.loads(buf)
                if expected_id is None or obj.get("id") == expected_id:
                    return obj
                else:
                    buf = ""
            except Exception:
                # Invalid JSON when accumulating; continue reading
                pass
    return None


def test_mcp_scan_nuget_project():
    """Test MCP Scan_Project tool with NuGet ecosystem on a temporary test project."""
    # Check if MCP SDK is available
    try:
        import mcp  # noqa: F401
        mcp_available = True
    except Exception:
        mcp_available = False
        # Skip test if MCP SDK not available
        import pytest
        pytest.skip("MCP SDK not available")

    # Create a temporary NuGet project with .csproj file
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "TestNuGetProject"
        project_dir.mkdir()

        # Create a .csproj file with some common NuGet packages
        csproj_content = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Newtonsoft.Json" Version="13.0.3" />
    <PackageReference Include="Microsoft.AspNetCore.OpenApi" Version="8.0.16" />
    <PackageReference Include="System.IdentityModel.Tokens.Jwt" Version="8.9.0" />
  </ItemGroup>
</Project>"""
        (project_dir / "TestNuGetProject.csproj").write_text(csproj_content, encoding="utf-8")

        env = os.environ.copy()
        env.update({
            "PYTHONPATH": f"{ROOT / 'src'}",
        })

        proc = _spawn_mcp_stdio(env)
        try:
            # Wait for server to start
            time.sleep(0.5)
            if proc.poll() is not None:
                outs, errs = proc.communicate(timeout=2)
                raise AssertionError(f"MCP server exited immediately. stderr: {errs}")

            # Initialize MCP connection
            assert proc.stdin is not None and proc.stdout is not None
            init_req = _rpc_envelope(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "clientInfo": {"name": "pytest", "version": "0.0.0"},
                    "capabilities": {},
                },
                id_=1,
            )
            try:
                _send_json(proc, init_req)
            except BrokenPipeError:
                raise AssertionError("MCP stdio not available: server closed pipe on initialize")

            init_resp = _read_json_response(proc, expected_id=1, timeout=5)
            assert init_resp is not None, "No initialize response from MCP server"
            assert init_resp.get("error") is None, f"Initialize error: {init_resp.get('error')}"

            # Call Scan_Project with NuGet ecosystem
            call = _rpc_envelope(
                "tools/call",
                {
                    "name": "Scan_Project",
                    "arguments": {
                        "projectDir": str(project_dir),
                        "ecosystem": "nuget",
                        "analysisLevel": "heur"
                    },
                },
                id_=2,
            )
            try:
                _send_json(proc, call)
            except BrokenPipeError:
                raise AssertionError("MCP stdio not available: server closed pipe on tools/call Scan_Project")

            # Read response with longer timeout for real network calls
            scan_resp = _read_json_response(proc, expected_id=2, timeout=120)
            assert scan_resp is not None, "No Scan_Project result from MCP server"

            # Check for errors
            error = scan_resp.get("error")
            if error:
                error_msg = error.get("message", "") if isinstance(error, dict) else str(error)
                raise AssertionError(f"Scan_Project error: {error_msg}")

            result = scan_resp.get("result")
            assert isinstance(result, dict), f"Expected dict result, got {type(result)}"

            # FastMCP may wrap structured output in structuredContent - extract if present
            if "structuredContent" in result:
                result = result["structuredContent"]

            # Verify result structure
            assert "packages" in result, "Result missing 'packages' field"
            assert isinstance(result["packages"], list), "Result 'packages' should be a list"
            assert "summary" in result, "Result missing 'summary' field"
            assert isinstance(result["summary"], dict), "Result 'summary' should be a dict"

            summary = result["summary"]
            assert "count" in summary, "Summary missing 'count' field"
            assert isinstance(summary["count"], int), "Summary 'count' should be an integer"

            # Verify we got packages
            package_count = summary["count"]
            assert package_count > 0, f"Expected packages found, got {package_count}"
            assert len(result["packages"]) == package_count, "Package list length should match summary count"

            # Verify package structure
            if result["packages"]:
                first_pkg = result["packages"][0]
                assert "name" in first_pkg, "Package missing 'name' field"
                assert "ecosystem" in first_pkg, "Package missing 'ecosystem' field"
                assert first_pkg["ecosystem"] == "nuget", f"Expected ecosystem 'nuget', got '{first_pkg['ecosystem']}'"
                assert "version" in first_pkg or "exists" in first_pkg, "Package should have 'version' or 'exists' field"

            # Verify we found expected packages from our test .csproj
            package_names = [pkg.get("name") for pkg in result["packages"]]
            assert "Newtonsoft.Json" in package_names, f"Expected to find Newtonsoft.Json, got: {package_names}"
            assert any("Microsoft" in name or "System" in name for name in package_names), \
                f"Expected to find Microsoft or System packages, got: {package_names}"

            # Verify packages have versions (indicating they were found in registry)
            # MCP output doesn't include 'exists' field, but packages with versions were found
            packages_with_versions = [pkg for pkg in result["packages"] if pkg.get("version")]
            assert len(packages_with_versions) > 0, "Expected at least some packages to have resolved versions (indicating registry lookup succeeded)"

            print(f"\n✓ MCP NuGet scan successful: {package_count} packages found, {len(packages_with_versions)} with resolved versions")

        finally:
            try:
                if proc.stdin:
                    proc.stdin.close()
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                # Process may already be terminated; ignore cleanup errors
                pass


def test_mcp_scan_nuget_project_auto_detect():
    """Test MCP Scan_Project tool with auto-detected NuGet ecosystem."""
    # Check if MCP SDK is available
    try:
        import mcp  # noqa: F401
        mcp_available = True
    except Exception:
        mcp_available = False
        import pytest
        pytest.skip("MCP SDK not available")

    # Create a temporary NuGet project with .csproj file
    with tempfile.TemporaryDirectory() as tmpdir:
        project_dir = Path(tmpdir) / "AutoDetectProject"
        project_dir.mkdir()

        # Create a .csproj file - auto-detection should find this
        csproj_content = """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0</TargetFramework>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="NLog.Web.AspNetCore" Version="5.4.0" />
    <PackageReference Include="Swashbuckle.AspNetCore" Version="8.1.1" />
  </ItemGroup>
</Project>"""
        (project_dir / "AutoDetectProject.csproj").write_text(csproj_content, encoding="utf-8")

        env = os.environ.copy()
        env.update({
            "PYTHONPATH": f"{ROOT / 'src'}",
        })

        proc = _spawn_mcp_stdio(env)
        try:
            time.sleep(0.5)
            if proc.poll() is not None:
                outs, errs = proc.communicate(timeout=2)
                raise AssertionError(f"MCP server exited immediately. stderr: {errs}")

            assert proc.stdin is not None and proc.stdout is not None
            init_req = _rpc_envelope(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "clientInfo": {"name": "pytest", "version": "0.0.0"},
                    "capabilities": {},
                },
                id_=3,
            )
            _send_json(proc, init_req)
            _read_json_response(proc, expected_id=3, timeout=5)

            # Call Scan_Project without specifying ecosystem (should auto-detect NuGet)
            call = _rpc_envelope(
                "tools/call",
                {
                    "name": "Scan_Project",
                    "arguments": {
                        "projectDir": str(project_dir),
                        "analysisLevel": "compare"
                    },
                },
                id_=4,
            )
            _send_json(proc, call)

            scan_resp = _read_json_response(proc, expected_id=4, timeout=120)
            assert scan_resp is not None, "No Scan_Project result from MCP server"
            assert scan_resp.get("error") is None, f"Scan_Project error: {scan_resp.get('error')}"

            result = scan_resp.get("result")
            if "structuredContent" in result:
                result = result["structuredContent"]

            assert "packages" in result
            assert len(result["packages"]) > 0, "Expected packages from auto-detected NuGet project"

            # Verify ecosystem is nuget
            if result["packages"]:
                assert result["packages"][0].get("ecosystem") == "nuget", \
                    "Auto-detected ecosystem should be 'nuget'"

            # Verify we found the expected packages
            package_names = [pkg.get("name") for pkg in result["packages"]]
            assert "NLog.Web.AspNetCore" in package_names or "Swashbuckle.AspNetCore" in package_names, \
                f"Expected to find test packages, got: {package_names}"

            print(f"\n✓ MCP NuGet auto-detection successful: {len(result['packages'])} packages found")

        finally:
            try:
                if proc.stdin:
                    proc.stdin.close()
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                pass
