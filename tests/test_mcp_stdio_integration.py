import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest


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
                pass
    return None


def test_mcp_stdio_initialize_and_lookup_latest_version_smoke(monkeypatch):
    # If MCP SDK isn't available, verify graceful failure of the subcommand instead of skipping
    try:
        import mcp  # noqa: F401
        mcp_available = True
    except Exception:
        mcp_available = False

    env = os.environ.copy()
    # Use fake registries to avoid real network. Ensure src and e2e_mocks are on PYTHONPATH.
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
            id_=11,
        )
        try:
            _send_json(proc, init_req)
        except BrokenPipeError:
            # Server closed pipe unexpectedly; treat as failure of transport
            raise AssertionError("MCP stdio not available: server closed pipe on initialize")
        # Some servers may not send a direct response to initialize; continue to tools/list
        _ = _read_json_response(proc, expected_id=11, timeout=1)

        # List tools next
        list_req = _rpc_envelope("tools/list", {}, id_=1)
        try:
            _send_json(proc, list_req)
        except BrokenPipeError:
            raise AssertionError("MCP stdio not available: server closed pipe on tools/list")
        response = _read_json_response(proc, expected_id=1, timeout=5)
        stderr_tail = ""
        if proc.stderr is not None:
            try:
                stderr_tail = proc.stderr.read() or ""
            except Exception:
                stderr_tail = ""
        assert response is not None, f"No response from MCP server. Stderr: {stderr_tail}"

        # Quick sanity: our tools should be listed
        tools = response.get("result", {}).get("tools", []) if isinstance(response.get("result"), dict) else []
        tool_names = {t.get("name") for t in tools} if isinstance(tools, list) else set()
        assert {"Lookup_Latest_Version", "Scan_Project", "Scan_Dependency"}.issubset(tool_names)

        # Call Lookup_Latest_Version via tools/call envelope
        call = _rpc_envelope(
            "tools/call",
            {
                "name": "Lookup_Latest_Version",
                "arguments": {"name": "left-pad", "ecosystem": "npm"},
            },
            id_=2,
        )
        try:
            _send_json(proc, call)
        except BrokenPipeError:
            raise AssertionError("MCP stdio not available: server closed pipe on tools/call")

        # Read result
        lookup_resp = _read_json_response(proc, expected_id=2, timeout=5)
        assert lookup_resp is not None, "No lookup result from MCP server"
        assert lookup_resp.get("error") is None, f"Lookup error: {lookup_resp.get('error')}"
        result = lookup_resp.get("result")
        assert isinstance(result, dict) and result.get("name") == "left-pad"
        assert result.get("ecosystem") == "npm"
    finally:
        try:
            if proc.stdin:
                proc.stdin.close()
            proc.terminate()
        except Exception:
            pass
