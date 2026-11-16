from datetime import datetime, timedelta

from conftest import NOW, day, jitter, make_series
from vitalsense.analysis import SleepNight, assess, sleep_consistency


def test_stable_series_is_typical():
    a = assess(make_series("resting_hr", lambda ago: 60 + jitter(ago) * 1.5), NOW)
    assert a.outcome == "typical"
    assert abs(a.baseline.median - 60) < 1
    assert a.baseline.count == 28
    assert a.recent.count == 7


def test_sustained_rise_is_flagged():
    s = make_series("resting_hr", lambda ago: 60 + jitter(ago) * 1.5 + (8 if ago < 7 else 0))
    f = assess(s, NOW).finding
    assert f is not None
    assert f.direction == "up"
    assert f.is_strong
    assert 6 < f.change < 10
    assert f.days_beyond_range >= 6
    assert f.confidence == "high"
    assert f.evidence
    assert any("not a medical assessment" in note for note in f.limitations)


def test_single_spike_is_not_flagged():
    # False-positive guard: one extreme day must not create a finding.
    s = make_series("heart_rate", lambda ago: 120 if ago == 2 else 72 + jitter(ago) * 2)
    assert assess(s, NOW).finding is None


def test_tiny_change_in_very_stable_data_is_not_flagged():
    s = make_series("resting_hr", lambda ago: 61 if ago < 7 else 60)
    assert assess(s, NOW).finding is None


def test_large_change_in_flat_data_is_flagged():
    s = make_series("resting_hr", lambda ago: 66 if ago < 7 else 60)
    assert assess(s, NOW).finding.direction == "up"


def test_decrease_is_flagged_downward():
    s = make_series("sleep", lambda ago: (6.0 if ago < 7 else 7.5) + jitter(ago) * 0.2)
    assert assess(s, NOW).finding.direction == "down"


def test_empty_series_is_insufficient():
    a = assess(make_series("steps", lambda ago: None), NOW)
    assert a.outcome == "insufficient"
    assert "No readings" in a.quality.issues[0]


def test_short_history_is_insufficient():
    a = assess(make_series("resting_hr", lambda ago: 60 + jitter(ago), days=12), NOW)
    assert a.outcome == "insufficient"
    assert "14" in a.reason


def test_sparse_recent_week_is_insufficient():
    def value(ago):
        if ago < 7:
            return 75 if ago in (0, 3, 5) else None
        return 60 + jitter(ago)
    a = assess(make_series("resting_hr", value), NOW)
    assert a.outcome == "insufficient"
    assert a.finding is None


def test_gaps_are_reported_in_data_quality():
    s = make_series("hrv", lambda ago: None if 10 <= ago <= 15 else 45 + jitter(ago) * 3)
    a = assess(s, NOW)
    assert a.quality.longest_gap_days == 6
    assert any("6 days" in issue for issue in a.quality.issues)


def test_implausible_readings_are_discarded():
    a = assess(make_series("resting_hr", lambda ago: 0 if ago == 20 else 60 + jitter(ago)), NOW)
    assert a.quality.discarded_readings == 1
    assert abs(a.baseline.median - 60) < 1


def test_cumulative_metrics_ignore_partial_today():
    s = make_series("steps", lambda ago: 1500 if ago == 0 else 9000 + jitter(ago) * 800)
    a = assess(s, NOW)
    assert a.finding is None
    assert a.recent.max > 8000


def test_trend_is_measured_per_week():
    a = assess(make_series("hrv", lambda ago: 40 + ago * 0.2), NOW)   # -1.4 ms per week
    assert abs(a.trend_per_week - -1.4) < 0.05


def night(days_ago: int, bed_minutes: float, hours: float = 7) -> SleepNight:
    morning = datetime.combine(day(days_ago), datetime.min.time())
    bed = morning + timedelta(minutes=bed_minutes)
    return SleepNight(day(days_ago), bed, bed + timedelta(hours=hours), hours)


def test_regular_schedule_across_midnight():
    # Bedtimes 23:45 and 00:15 alternate: only 30 minutes apart, not ~23 hours.
    nights = [night(i, -15 if i % 2 == 0 else 15) for i in range(14)]
    sc = sleep_consistency(nights, NOW)
    assert sc.bedtime_spread_minutes < 20
    assert sc.average_bedtime == (0, 0)


def test_not_enough_nights():
    assert sleep_consistency([night(i, -30) for i in range(3)], NOW) is None
