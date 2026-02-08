"""Utilities for supply-chain trust signal scoring and regression checks."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Optional, Tuple


def epoch_ms_from_iso8601(value: Optional[str]) -> Optional[int]:
    """Parse an ISO-8601 string into epoch milliseconds."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    try:
        if text.endswith("Z"):
            parsed = datetime.fromisoformat(text[:-1]).replace(tzinfo=timezone.utc)
        else:
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.timestamp() * 1000)
    except (ValueError, TypeError):
        return None


def age_days_from_epoch_ms(timestamp_ms: Optional[int]) -> Optional[int]:
    """Return package age in full days for an epoch-millis timestamp."""
    if timestamp_ms is None:
        return None
    try:
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        age = max(0, now_ms - int(timestamp_ms))
        return int(age // 86400000)
    except (ValueError, TypeError):
        return None


def score_from_boolean_signals(signals: Iterable[Optional[bool]]) -> Optional[float]:
    """Compute a normalized score from tri-state boolean signals.

    - True -> 1.0
    - False -> 0.0
    - None -> ignored
    """
    values = []
    for signal in signals:
        if signal is None:
            continue
        values.append(1.0 if bool(signal) else 0.0)
    if not values:
        return None
    return float(sum(values) / len(values))


def regressed(current: Optional[bool], previous: Optional[bool]) -> Optional[bool]:
    """Return True when previous=True and current=False, else tri-state."""
    if current is None or previous is None:
        return None
    return bool(previous and not current)


def score_delta(
    current_score: Optional[float],
    previous_score: Optional[float],
    threshold: float = 0.0,
) -> Tuple[Optional[float], Optional[bool]]:
    """Return (delta, decreased) for score comparison."""
    if current_score is None or previous_score is None:
        return None, None
    try:
        delta = float(current_score) - float(previous_score)
    except (ValueError, TypeError):
        return None, None
    floor = abs(float(threshold))
    return delta, bool(delta < (-1.0 * floor))
