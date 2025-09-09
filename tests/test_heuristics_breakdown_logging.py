import logging

import pytest

from analysis import heuristics as _heur
from metapackage import MetaPackage


@pytest.fixture(autouse=True)
def set_debug_logging():
    # Ensure DEBUG is enabled so heuristics emits breakdown logs
    logging.getLogger().setLevel(logging.DEBUG)
    yield


def test_score_breakdown_logging_in_debug(caplog):
    mp = MetaPackage("pkg")
    mp.exists = True
    # Provide some repo signals to exercise breakdown
    mp.repo_stars = 50
    mp.repo_contributors = 10
    mp.repo_present_in_registry = True
    mp.repo_last_activity_at = "2024-01-01T00:00:00+00:00"
    mp.repo_version_match = {"matched": False}

    with caplog.at_level(logging.DEBUG):
        _heur.run_heuristics([mp])

    # Look for breakdown record with extra fields
    records = [r for r in caplog.records if r.levelno == logging.DEBUG and getattr(r, "action", None) == "score_breakdown"]
    assert len(records) >= 1
    rec = records[0]

    # Validate expected structured extras exist
    assert getattr(rec, "component", None) == "heuristics"
    assert getattr(rec, "package_name", None) == "pkg"
    # Ensure breakdown dictionary and weights are present
    assert isinstance(getattr(rec, "breakdown", None), dict)
    assert isinstance(getattr(rec, "weights", None), dict)
    # Final score must be within [0,1]
    fs = getattr(rec, "final_score", None)
    assert isinstance(fs, float)
    assert 0.0 <= fs <= 1.0
