"""Unit tests for shared trust-signal helpers."""

from common.trust_signals import (
    epoch_ms_from_iso8601,
    score_from_boolean_signals,
    regressed,
    score_delta,
)


def test_epoch_ms_from_iso8601_valid():
    assert epoch_ms_from_iso8601("2024-01-01T00:00:00Z") is not None


def test_score_from_boolean_signals():
    assert score_from_boolean_signals([True, False]) == 0.5
    assert score_from_boolean_signals([None, None]) is None


def test_score_from_boolean_signals_weighted():
    assert score_from_boolean_signals([True, False], weights=[0.8, 0.2]) == 0.8
    assert score_from_boolean_signals([False, True], weights=[0.8, 0.2]) == 0.2


def test_regressed():
    assert regressed(False, True) is True
    assert regressed(True, True) is False
    assert regressed(None, True) is None


def test_score_delta():
    delta, decreased = score_delta(0.5, 1.0, threshold=0.1)
    assert delta == -0.5
    assert decreased is True
