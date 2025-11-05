import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "src" / "depgate.py"


def _spawn_mcp_stdio(env=None):
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
    return json.dumps({"jsonrpc": "2.0", "id": id_, "method": method, "params": params or {}}) + "\n"


def _send_json(proc, payload_str: str) -> None:
    assert proc.stdin is not None
    proc.stdin.write(payload_str)
    proc.stdin.flush()


def _read_json_response(proc, expected_id=None, timeout=5):
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


def test_mcp_scan_project_integration_smoke(monkeypatch, tmp_path):
    # If MCP SDK isn't available, verify graceful subcommand failure instead of skipping
    try:
        import mcp  # noqa: F401
        mcp_available = True
    except Exception:
        mcp_available = False

    # Create a tiny npm project in a temp dir using existing tests fixtures as reference
    project_dir = tmp_path / "proj"
    project_dir.mkdir(parents=True, exist_ok=True)
    pkg_json = {
        "name": "scan-smoke",
        "version": "1.0.0",
        "dependencies": {
            "left-pad": "^1.3.0"
        }
    }
    (project_dir / "package.json").write_text(json.dumps(pkg_json), encoding="utf-8")

    env = os.environ.copy()
    env.update({
        "FAKE_REGISTRY": "1",
        "PYTHONPATH": f"{ROOT / 'tests' / 'e2e_mocks'}:{ROOT / 'src'}",
    })

    proc = _spawn_mcp_stdio(env)
    try:
        # If server exited immediately (e.g., fastmcp missing), assert graceful error
        time.sleep(0.2)
        if not mcp_available or proc.poll() is not None:
            outs, errs = proc.communicate(timeout=2)
            assert proc.returncode != 0
            assert "MCP server not available" in (errs or "")
            return

        # Initialize first per MCP
        assert proc.stdin is not None and proc.stdout is not None
        init_req = _rpc_envelope(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "clientInfo": {"name": "pytest", "version": "0.0.0"},
                "capabilities": {},
            },
            id_=21,
        )
        try:
            _send_json(proc, init_req)
        except BrokenPipeError:
            raise AssertionError("MCP stdio not available: server closed pipe on initialize")
        _ = _read_json_response(proc, expected_id=21, timeout=1)

        # Call Scan_Project via tools/call envelope
        call = _rpc_envelope(
            "tools/call",
            {
                "name": "Scan_Project",
                "arguments": {
                    "projectDir": str(project_dir),
                    "ecosystem": "npm",
                    "analysisLevel": "compare"
                },
            },
            id_=22,
        )
        try:
            _send_json(proc, call)
        except BrokenPipeError:
            raise AssertionError("MCP stdio not available: server closed pipe on tools/call Scan_Project")

        scan_resp = _read_json_response(proc, expected_id=22, timeout=10)
        assert scan_resp is not None, "No Scan_Project result from MCP server"
        assert scan_resp.get("error") is None, f"Scan_Project error: {scan_resp.get('error')}"
        result = scan_resp.get("result")
        assert isinstance(result, dict)
        # FastMCP may wrap structured output in structuredContent - extract if present
        if "structuredContent" in result:
            result = result["structuredContent"]
        # Minimal golden-shape checks according to tightened schema
        assert "packages" in result and isinstance(result["packages"], list)
        assert "summary" in result and isinstance(result["summary"], dict)
        assert isinstance(result["summary"].get("count"), int)
        # When using FAKE_REGISTRY, resolution should still return at least 1 package from manifest
        assert result["summary"]["count"] >= 1
        first = result["packages"][0] if result["packages"] else {}
        assert first.get("name") == "left-pad"
        assert first.get("ecosystem") == "npm"
    finally:
        try:
            if proc.stdin:
                proc.stdin.close()
            proc.terminate()
        except Exception:
            # Process may already be terminated; ignore cleanup errors
            pass
