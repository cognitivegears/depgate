"""Tests for release-age and trust-regression heuristics."""

import time

from analysis import heuristics as _heur
from constants import Constants
from metapackage import MetaPackage


def test_min_release_age_threshold_risk(monkeypatch):
    """Packages newer than configured minimum age should be flagged."""
    mp = MetaPackage("pkg", "npm")
    mp.timestamp = int((time.time() - 1 * 86400) * 1000)  # 1 day old
    monkeypatch.setattr(Constants, "HEURISTICS_MIN_RELEASE_AGE_DAYS", 3)

    _heur.test_timestamp(mp)

    assert mp.risk_too_new is True
    assert isinstance(mp.release_age_days, int)
    assert mp.release_age_days <= 1


def test_min_release_age_threshold_pass(monkeypatch):
    """Packages older than configured minimum age should pass the new-age check."""
    mp = MetaPackage("pkg", "npm")
    mp.timestamp = int((time.time() - 5 * 86400) * 1000)  # 5 days old
    monkeypatch.setattr(Constants, "HEURISTICS_MIN_RELEASE_AGE_DAYS", 3)

    _heur.test_timestamp(mp)

    assert mp.risk_too_new is False
    assert mp.release_age_days >= 5


def test_trust_regression_flags(monkeypatch):
    """Trust regression should set dedicated risk flags."""
    mp = MetaPackage("pkg", "npm")
    mp.provenance_regressed = True
    mp.registry_signature_regressed = True
    mp.trust_score_delta = -0.2
    monkeypatch.setattr(Constants, "HEURISTICS_SCORE_DECREASE_THRESHOLD", 0.1)

    _heur.test_trust_regression(mp)

    assert mp.risk_provenance_regression is True
    assert mp.risk_registry_signature_regression is True
    assert mp.risk_score_decrease is True


def test_trust_regression_score_threshold(monkeypatch):
    """Small score deltas under threshold should not trigger score decrease risk."""
    mp = MetaPackage("pkg", "npm")
    mp.provenance_regressed = False
    mp.registry_signature_regressed = False
    mp.trust_score_delta = -0.05
    monkeypatch.setattr(Constants, "HEURISTICS_SCORE_DECREASE_THRESHOLD", 0.1)

    _heur.test_trust_regression(mp)

    assert mp.risk_provenance_regression is False
    assert mp.risk_registry_signature_regression is False
    assert mp.risk_score_decrease is False
