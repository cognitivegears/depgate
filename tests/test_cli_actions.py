import os
import subprocess
import sys
from pathlib import Path


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _src_entry() -> Path:
    return _project_root() / "src" / "depgate.py"


def _run_cli(args, env_overrides=None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-u", str(_src_entry()), *args]
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        cmd,
        cwd=str(_project_root()),
        text=True,
        capture_output=True,
        env=env,
    )


def test_root_help_shows_actions():
    proc = _run_cli(["--help"])
    # Argparse prints help to stdout and exits 0
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    # Usage summary with actions overview
    assert "Actions" in proc.stdout, f"Root help missing Actions section:\n{proc.stdout}"
    assert "scan" in proc.stdout, f"Root help missing 'scan' action:\n{proc.stdout}"
    assert "depgate" in proc.stdout, f"Root help missing program name:\n{proc.stdout}"
    # Hint for per-action help
    assert "depgate <action> --help" in proc.stdout or "depgate <action> --help" in proc.stdout


def test_scan_help_lists_options():
    proc = _run_cli(["scan", "--help"])
    assert proc.returncode == 0, f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    # Option summary includes -t/--type and description
    assert ("-t" in proc.stdout or "--type" in proc.stdout), f"Scan help missing -t/--type:\n{proc.stdout}"
    assert "Package Manager Type" in proc.stdout, f"Scan help missing type description:\n{proc.stdout}"
    # Mutually exclusive inputs shown
    assert any(s in proc.stdout for s in ("--package", "--directory", "--load_list")), proc.stdout


def test_unknown_action_errors():
    proc = _run_cli(["bogus"])
    # Non-zero exit
    assert proc.returncode != 0, "Unknown action should exit non-zero"
    combined = (proc.stderr or "") + (proc.stdout or "")
    # Accept either argparse invalid choice or our custom message; both list 'scan'
    assert ("invalid choice" in combined) or ("Unknown action" in combined), combined
    assert "scan" in combined, combined


def test_legacy_no_action_maps_to_scan_warns_once():
    # Use the e2e fake registry to avoid real network; ensure sitecustomize is imported
    env = {
        "FAKE_REGISTRY": "1",
        "PYTHONPATH": f"{_project_root() / 'tests' / 'e2e_mocks'}:{_project_root() / 'src'}"
    }
    # Legacy invocation: no action token, options-first. This should map to 'scan' and emit a single deprecation warning.
    proc = _run_cli(["-t", "npm", "-p", "left-pad", "-a", "compare"], env_overrides=env)
    assert proc.returncode == 0, f"Expected success. stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    # Count deprecation warnings printed once
    deprecations = [ln for ln in (proc.stderr or "").splitlines() if "DEPRECATION:" in ln]
    assert len(deprecations) == 1, f"Expected 1 deprecation warning, got {len(deprecations)}.\nStderr:\n{proc.stderr}"
