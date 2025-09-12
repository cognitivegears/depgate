from behave import given, when, then
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

def find_project_root(start: Path) -> Path:
    cur = start
    for _ in range(10):
        if (cur / "pyproject.toml").exists() or (cur / "src").exists():
            return cur
        cur = cur.parent
    # Fallback: go up 4 levels which should normally be project root
    return start.parents[4]

PROJECT_ROOT = find_project_root(Path(__file__).resolve())
SRC_ENTRY = PROJECT_ROOT / "src" / "depgate.py"
ARTIFACTS = PROJECT_ROOT / "tests" / "e2e" / "artifacts"
MOCKS_DIR = PROJECT_ROOT / "tests" / "e2e_mocks"

def _ensure_artifacts():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    return ARTIFACTS

def _unique_name(prefix, ext):
    return f"{prefix}-{uuid.uuid4().hex[:8]}.{ext}"

def _resolve_placeholder(val, context):
    # Map placeholders to generated paths (idempotent within a scenario)
    if val in ("<json_path>", "<json_path>"):
        if getattr(context, "json_path", None):
            return context.json_path
        context.json_path = str(_ensure_artifacts() / _unique_name("out", "json"))
        return context.json_path
    if val in ("<csv_path>", "<csv_path>"):
        if getattr(context, "csv_path", None):
            return context.csv_path
        context.csv_path = str(_ensure_artifacts() / _unique_name("out", "csv"))
        return context.csv_path
    if val in ("<tmp_dir>", "<tmp_dir>"):
        return getattr(context, "tmp_dir")
    if val in ("<list_file>", "<list_file>"):
        return getattr(context, "list_file")
    return val

@given("fake registries are enabled")
def step_enable_fakes(context):
    context.fake_enabled = True

@given('fake registry mode "{mode}"')
def step_fake_mode(context, mode):
    context.fake_mode = mode

@given("a clean artifacts directory")
def step_clean_artifacts(context):
    if ARTIFACTS.exists():
        for p in ARTIFACTS.iterdir():
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                shutil.rmtree(p)
    _ensure_artifacts()

@given("a temp directory with package.json:")
def step_temp_pkgjson(context):
    tmp_dir = Path(tempfile.mkdtemp(prefix="dg-npm-"))
    (tmp_dir / "package.json").write_text(context.text, encoding="utf-8")
    context.tmp_dir = str(tmp_dir)

@given("a temp directory with requirements.txt:")
def step_temp_requirements(context):
    tmp_dir = Path(tempfile.mkdtemp(prefix="dg-pypi-"))
    (tmp_dir / "requirements.txt").write_text(context.text, encoding="utf-8")
    context.tmp_dir = str(tmp_dir)

@given("a temp directory with pom.xml:")
def step_temp_pom(context):
    tmp_dir = Path(tempfile.mkdtemp(prefix="dg-maven-"))
    (tmp_dir / "pom.xml").write_text(context.text, encoding="utf-8")
    context.tmp_dir = str(tmp_dir)

@given('a package list file containing "{artifact}"')
def step_pkg_list_file(context, artifact):
    _ensure_artifacts()
    path = ARTIFACTS / _unique_name("pkgs", "lst")
    # Supply a default group for testing
    path.write_text(f"com.example:{artifact}\n", encoding="utf-8")
    context.list_file = str(path)

@when("I run depgate with arguments:")
def step_run_depgate(context):
    args = []
    action_token = None
    help_present = False

    for row in context.table:
        arg = row["arg"].strip()
        val = row["value"].strip()

        # Allow specifying positional action explicitly
        if arg.lower() in ("action", "<action>"):
            action_token = _resolve_placeholder(val, context)
            continue

        if arg in ("-h", "--help"):
            help_present = True

        # Interpret boolean flags passed as "true"
        if val.lower() == "true":
            args.append(arg)
        else:
            args.extend([arg, _resolve_placeholder(val, context)])

    # Default to 'scan' action unless explicitly suppressed or asking for root help
    if not action_token and not help_present and not getattr(context, "legacy_no_action", False):
        action_token = "scan"

    cmd = ["uv", "run", "-q", str(SRC_ENTRY)]
    if action_token:
        cmd.append(action_token)
    cmd.extend(args)

    env = os.environ.copy()
    # Ensure our mocks and src are importable (sitecustomize is auto-imported)
    env["PYTHONPATH"] = f"{MOCKS_DIR}:{PROJECT_ROOT / 'src'}:" + env.get("PYTHONPATH", "")
    if getattr(context, "fake_enabled", False):
        env["FAKE_REGISTRY"] = "1"
    if getattr(context, "fake_mode", ""):
        env["FAKE_MODE"] = context.fake_mode

    proc = subprocess.run(
        cmd,
        cwd=str(PROJECT_ROOT),
        text=True,
        capture_output=True,
        env=env,
    )
    context.proc = proc

@then("the process exits with code {code:d}")
def step_exit_code(context, code):
    assert context.proc.returncode == code, f"Expected {code}, got {context.proc.returncode}\nSTDOUT:\n{context.proc.stdout}\nSTDERR:\n{context.proc.stderr}"

@then('stdout is empty or whitespace only')
def step_stdout_quiet(context):
    assert context.proc.stdout.strip() == "", f"Expected empty stdout, got:\n{context.proc.stdout}"

def _get_nested(record, dotted):
    cur = record
    for part in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur

def _parse_expected(value: str):
    v = value.strip()
    if v.lower() == "true":
        return True
    if v.lower() == "false":
        return False
    return v

@then('the JSON output at "{path_key}" contains 1 record for "{pkg}" with:')
def step_json_one_record_with(context, path_key, pkg):
    path = _resolve_placeholder(path_key, context)
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    matches = [r for r in data if r.get("packageName") == pkg]
    assert len(matches) == 1, f"Expected exactly 1 record for {pkg}, found {len(matches)}. Data: {data}"
    record = matches[0]
    for row in context.table:
        field = row["field"].strip()
        expected = _parse_expected(row["expected"])
        cur = _get_nested(record, field)
        if row["expected"].strip() == "":
            continue
        assert cur == expected, f"Field {field} expected {expected}, got {cur}"

@then('the JSON output at "{path_key}" record for "{pkg}" has risk flags:')
def step_json_record_risks(context, path_key, pkg):
    path = _resolve_placeholder(path_key, context)
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    record = next((r for r in data if r.get("packageName") == pkg), None)
    assert record is not None, f"No record for {pkg} in {data}"
    for row in context.table:
        field = row["field"].strip()
        expected = row["expected"].strip()
        if expected == "":
            continue
        exp_val = _parse_expected(expected)
        cur = _get_nested(record, field)
        assert cur == exp_val, f"Field {field} expected {exp_val}, got {cur}"

@then('the JSON output at "{path_key}" contains records for:')
def step_json_contains_records(context, path_key):
    path = _resolve_placeholder(path_key, context)
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    names = {r.get("packageName") for r in data}
    expected = {row["packageName"].strip() for row in context.table}
    missing = expected - names
    assert not missing, f"Missing records for: {missing}. Present: {names}"

@then('the JSON output at "{path_key}" record for "{pkg}" has fields:')
def step_json_record_fields(context, path_key, pkg):
    path = _resolve_placeholder(path_key, context)
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    record = next((r for r in data if r.get("packageName") == pkg), None)
    assert record is not None, f"No record for {pkg} in {data}"
    for row in context.table:
        field = row["field"].strip()
        expected = row["expected"].strip()
        if expected == "":
            continue
        exp_val = _parse_expected(expected)
        cur = _get_nested(record, field)
        assert cur == exp_val, f"Field {field} expected {exp_val}, got {cur}"

@then('the CSV at "{path_key}" has a header row and 2 rows total')
def step_csv_two_rows(context, path_key):
    path = _resolve_placeholder(path_key, context)
    with open(path, "r", encoding="utf-8") as f:
        lines = [ln.rstrip("\n") for ln in f.readlines()]
    assert len(lines) == 2, f"Expected 2 lines (header+1), got {len(lines)}. Lines: {lines}"
    assert "," in lines[0], "Header row appears malformed"
