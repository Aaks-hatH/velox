"""
Shared test helpers: a fixed "now" so tests never depend on today's date,
and a quick way to build a series from a rule like "60 bpm, except the last week".
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # so `import vitalsense` works

from vitalsense.analysis import DailyValue, Series  # noqa: E402
from vitalsense.metrics import METRICS  # noqa: E402

NOW = datetime(2026, 3, 15, 12, 0)
TODAY = NOW.date()


def day(days_ago: int):
    return TODAY - timedelta(days=days_ago)


def make_series(metric_id: str, value_for_day, days: int = 40) -> Series:
    """value_for_day(days_ago) returns a number, or None for a missing day."""
    values = []
    for days_ago in range(days - 1, -1, -1):
        v = value_for_day(days_ago)
        if v is not None:
            values.append(DailyValue(day(days_ago), v))
    return Series(METRICS[metric_id], values, NOW if values else None, is_demo=True)


def jitter(i: int) -> float:
    """Small repeatable wobble in [-1, 1]."""
    return [0.0, 0.6, -0.4, 0.9, -0.8, 0.3, -0.2, 0.7, -0.6, 0.1][i % 10]
