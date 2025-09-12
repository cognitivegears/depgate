import json
import pytest

from depgate import export_json
from cli_build import determine_exit_code
from metapackage import MetaPackage
from constants import ExitCodes


def test_export_json_includes_linked_fields_only_in_linked_mode(tmp_path):
    # Prepare a package marked as linked mode
    mp = MetaPackage("pkg-linked", "npm")
    setattr(mp, "_linked_mode", True)
    mp.repo_url_normalized = "https://github.com/owner/repo"
    mp.repo_version_match = {
        "matched": True,
        "match_type": "exact",
        "artifact": {"name": "1.2.3"},
        "tag_or_release": "1.2.3",
    }
    # Simulate provider_validation match sources captured for logging/diagnostics
    setattr(mp, "_linked_tag_match", True)
    setattr(mp, "_linked_release_match", False)
    setattr(mp, "linked", True)

    out1 = tmp_path / "linked.json"
    export_json([mp], str(out1))
    data1 = json.loads(out1.read_text(encoding="utf-8"))
    assert isinstance(data1, list) and len(data1) == 1
    rec1 = data1[0]
    # New fields should be present only in linked mode
    assert rec1.get("repositoryUrl") == "https://github.com/owner/repo"
    assert rec1.get("tagMatch") is True
    assert rec1.get("releaseMatch") is False
    assert rec1.get("linked") is True

    # Prepare a second package NOT in linked mode to ensure fields are absent
    mp2 = MetaPackage("pkg-nonlinked", "npm")
    mp2.repo_url_normalized = "https://gitlab.com/owner/repo"
    mp2.repo_version_match = {"matched": False, "match_type": None, "artifact": None, "tag_or_release": None}

    out2 = tmp_path / "nonlinked.json"
    export_json([mp2], str(out2))
    data2 = json.loads(out2.read_text(encoding="utf-8"))
    assert isinstance(data2, list) and len(data2) == 1
    rec2 = data2[0]
    # Linked-only fields should NOT be present when not in linked mode
    assert "repositoryUrl" not in rec2
    assert "tagMatch" not in rec2
    assert "releaseMatch" not in rec2
    assert "linked" not in rec2


def test_determine_exit_code_linked_success(monkeypatch):
    # Ensure a clean instances list
    MetaPackage.instances.clear()

    # Create packages all passing linkage
    mp1 = MetaPackage("ok1", "npm")
    mp2 = MetaPackage("ok2", "npm")
    for mp in (mp1, mp2):
        setattr(mp, "_linked_mode", True)
        setattr(mp, "linked", True)

    class Args:
        LEVEL = "linked"
        ERROR_ON_WARNINGS = False

    with pytest.raises(SystemExit) as e:
        determine_exit_code(Args())
    assert e.value.code == ExitCodes.SUCCESS.value


def test_determine_exit_code_linked_failure(monkeypatch):
    # Ensure a clean instances list
    MetaPackage.instances.clear()

    # One package fails linkage
    mp1 = MetaPackage("ok", "npm")
    mp2 = MetaPackage("bad", "npm")
    setattr(mp1, "_linked_mode", True)
    setattr(mp1, "linked", True)
    setattr(mp2, "_linked_mode", True)
    setattr(mp2, "linked", False)

    class Args:
        LEVEL = "linked"
        ERROR_ON_WARNINGS = False

    with pytest.raises(SystemExit) as e:
        determine_exit_code(Args())
    assert e.value.code == ExitCodes.FILE_ERROR.value
