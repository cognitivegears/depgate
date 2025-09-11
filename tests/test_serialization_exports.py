import csv
import json
from datetime import datetime, timezone

from depgate import export_json, export_csv
from metapackage import MetaPackage


def make_pkg(name="pkg", pkg_type="npm"):
    mp = MetaPackage(name, pkg_type)
    mp.exists = True
    mp.version_count = 3
    mp.timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
    return mp


def test_json_includes_repo_fields_defaults(tmp_path):
    mp = make_pkg()
    # Leave all repo_* fields as None
    out = tmp_path / "out.json"
    export_json([mp], str(out))

    data = json.loads(out.read_text(encoding="utf-8"))
    assert isinstance(data, list) and len(data) == 1
    rec = data[0]

    # Keys present with null defaults
    assert "repo_stars" in rec and rec["repo_stars"] is None
    assert "repo_contributors" in rec and rec["repo_contributors"] is None
    assert "repo_last_activity" in rec and rec["repo_last_activity"] is None
    assert "repo_present_in_registry" in rec and rec["repo_present_in_registry"] is None
    assert "repo_version_match" in rec and rec["repo_version_match"] is None


def test_csv_headers_and_defaults(tmp_path):
    mp = make_pkg()
    # Leave repo_* None to verify empty-string defaults
    out = tmp_path / "out.csv"
    export_csv([mp], str(out))

    rows = list(csv.reader(out.open("r", encoding="utf-8")))
    assert len(rows) == 2  # header + one data row

    header = rows[0]
    # New columns must be present and snake_cased
    assert header[-5:] == [
        "repo_stars",
        "repo_contributors",
        "repo_last_activity",
        "repo_present_in_registry",
        "repo_version_match",
    ]

    row = rows[1]
    # Empty string defaults in CSV for missing repo_* values
    assert row[-5:] == ["", "", "", "", ""]


def test_csv_with_values(tmp_path):
    mp = make_pkg()
    # Populate repo_* values
    mp.repo_stars = 10
    mp.repo_contributors = 3
    mp.repo_last_activity_at = "2024-01-01T00:00:00+00:00"
    mp.repo_present_in_registry = True
    mp.repo_version_match = {"matched": True}

    out = tmp_path / "out_values.csv"
    export_csv([mp], str(out))
    rows = list(csv.reader(out.open("r", encoding="utf-8")))
    assert len(rows) == 2

    row = rows[1]
    # Stars and contributors should serialize as numbers (stringified by csv)
    assert row[-5] == "10"
    assert row[-4] == "3"
    # Last activity should be a non-empty ISO string
    assert isinstance(row[-3], str) and len(row[-3]) > 0
    # Present in registry and version match become True/False strings
    assert row[-2] == "True"
    assert row[-1] == "True"


def test_json_includes_dependency_fields_defaults(tmp_path):
    mp = make_pkg()
    out = tmp_path / "out_dep.json"
    export_json([mp], str(out))

    data = json.loads(out.read_text(encoding="utf-8"))
    rec = data[0]
    assert "dependency_relation" in rec and rec["dependency_relation"] is None
    assert "dependency_requirement" in rec and rec["dependency_requirement"] is None
    assert "dependency_scope" in rec and rec["dependency_scope"] is None


def test_csv_headers_include_dependency_fields(tmp_path):
    mp = make_pkg()
    out = tmp_path / "out_dep.csv"
    export_csv([mp], str(out))

    rows = list(csv.reader(out.open("r", encoding="utf-8")))
    header = rows[0]
    # New dependency columns present
    assert "dependency_relation" in header
    assert "dependency_requirement" in header
    assert "dependency_scope" in header
    # repo_* remain last five
    assert header[-5:] == [
        "repo_stars",
        "repo_contributors",
        "repo_last_activity",
        "repo_present_in_registry",
        "repo_version_match",
    ]
    # dependency columns appear before repo_stars
    assert header.index("dependency_relation") < header.index("repo_stars")


def test_json_and_csv_dependency_values(tmp_path):
    mp = make_pkg()
    mp.dependency_relation = "direct"
    mp.dependency_requirement = "required"
    mp.dependency_scope = "development"

    # JSON
    outj = tmp_path / "out_dep_values.json"
    export_json([mp], str(outj))
    rec = json.loads(outj.read_text(encoding="utf-8"))[0]
    assert rec["dependency_relation"] == "direct"
    assert rec["dependency_requirement"] == "required"
    assert rec["dependency_scope"] == "development"

    # CSV
    outc = tmp_path / "out_dep_values.csv"
    export_csv([mp], str(outc))
    rows = list(csv.reader(outc.open("r", encoding="utf-8")))
    header = rows[0]
    row = rows[1]
    i_rel = header.index("dependency_relation")
    i_req = header.index("dependency_requirement")
    i_sco = header.index("dependency_scope")
    assert row[i_rel] == "direct"
    assert row[i_req] == "required"
    assert row[i_sco] == "development"
