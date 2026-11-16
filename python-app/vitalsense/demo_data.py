"""
Fictional data for Demo Mode. Nothing here is a real person's data.

The data is generated, not stored, so it is always dated relative to today.
A fixed random seed means every run tells the same story:
  - Resting HR: stable for months, then higher for the last ~6 days   -> flagged (up)
  - HRV: slow decline over 3 months                                  -> a trend, not flagged
  - Heart rate: stable with ONE spike day                            -> correctly NOT flagged
  - Sleep: ~7 h 25 min, then ~6 h last week, later bedtimes          -> flagged (down)
  - Wrist temperature: recent nights missing                         -> "needs more data"
  - Breathing, steps, distance: normal variation                     -> usual

Used by: app.py when Demo Mode is on; tests.
"""

import math
from datetime import datetime, timedelta

from .analysis import DailyValue, Series, SleepNight, Snapshot, build_snapshot
from .metrics import ALL_METRICS, METRICS

HISTORY_DAYS = 90
NOT_WORN_DAYS = {17, 33, 34, 52, 71}   # days the watch wasn't worn


class SeededRandom:
    """
    Repeatable random numbers (the SplitMix64 algorithm), so demo data is identical every run.
    Python's own `random` would also work; this keeps the numbers identical on every computer.
    """
    MASK = 2**64 - 1

    def __init__(self, seed: int):
        self.state = seed & self.MASK

    def next_int(self) -> int:
        self.state = (self.state + 0x9E3779B97F4A7C15) & self.MASK
        z = self.state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & self.MASK
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & self.MASK
        return z ^ (z >> 31)

    def uniform(self) -> float:
        """A number from 0 up to (not including) 1."""
        return (self.next_int() >> 11) / 2**53

    def gaussian(self) -> float:
        """A bell-curve number with average 0 and spread 1 (Box-Muller method)."""
        u1 = max(self.uniform(), 1e-300)
        u2 = self.uniform()
        return math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)


def seed_for(metric_id: str) -> int:
    position = [m.id for m in ALL_METRICS].index(metric_id) + 1
    return (position * 0x9E3779B97F4A7C15) & SeededRandom.MASK


def demo_snapshot(now: datetime, metric_ids: list[str] | None = None) -> Snapshot:
    """The full demo: every chosen measurement, analysed."""
    metric_ids = metric_ids or [m.id for m in ALL_METRICS]
    series = {metric_id: demo_series(metric_id, now) for metric_id in metric_ids}
    nights = demo_sleep_nights(now, days=35) if "sleep" in metric_ids else []
    return build_snapshot(series, nights, now, is_demo=True)


def demo_series(metric_id: str, now: datetime) -> Series:
    metric = METRICS[metric_id]
    if metric_id == "sleep":
        nights = demo_sleep_nights(now)
        days = [DailyValue(n.day, n.asleep_hours) for n in nights]
        last = nights[-1].wake_time if nights else None
        return Series(metric, days, last, is_demo=True)

    rng = SeededRandom(seed_for(metric_id))
    today = now.date()
    days = []
    for days_ago in range(HISTORY_DAYS - 1, -1, -1):
        noise = rng.gaussian()   # always draw, so skipped days don't shift later values
        value = demo_value(metric_id, days_ago, today - timedelta(days=days_ago), noise, now)
        if value is not None:
            days.append(DailyValue(today - timedelta(days=days_ago), value))
    return Series(metric, days, now - timedelta(minutes=11), is_demo=True)


def demo_value(metric_id: str, days_ago: int, day, noise: float, now: datetime) -> float | None:
    if not METRICS[metric_id].is_activity and days_ago in NOT_WORN_DAYS:
        return None

    if metric_id == "resting_hr":
        rise = 4.0 + (5 - days_ago) * 0.6 if days_ago <= 5 else 0
        return 58 + noise * 1.3 + rise
    if metric_id == "hrv":
        return 43 + days_ago * 0.1 + noise * 4.5        # ~9 ms higher three months ago
    if metric_id == "heart_rate":
        return 91 if days_ago == 2 else 73 + noise * 2.2   # one odd day: must NOT be flagged
    if metric_id == "breathing":
        return 14.6 + noise * 0.4
    if metric_id == "wrist_temp":
        if 1 <= days_ago <= 6 and days_ago != 3:
            return None                                  # recent nights missing
        return 36.3 + noise * 0.12
    if metric_id == "steps":
        return demo_steps(days_ago, day, now)
    if metric_id == "distance":
        return demo_steps(days_ago, day, now) * 0.00076
    return None


def demo_steps(days_ago: int, day, now: datetime) -> float:
    # Steps and distance share the same noise so they stay consistent with each other.
    noise = SeededRandom(0xA11CE + days_ago).gaussian()
    weekend = day.weekday() >= 5
    total = max(1200, (11_200 if weekend else 8_600) + noise * 1_700)
    if days_ago == 0:
        # Today isn't over yet, so only part of the day's steps exist.
        progress = (now - now.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds() / 86_400
        return total * min(1, max(0.02, progress))
    return total


def demo_sleep_nights(now: datetime, days: int = HISTORY_DAYS) -> list[SleepNight]:
    rng = SeededRandom(seed_for("sleep"))
    midnight_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    nights = []
    for days_ago in range(days - 1, -1, -1):
        bed_noise, length_noise = rng.gaussian(), rng.gaussian()
        if days_ago in (26, 58):
            continue                                       # watch not worn
        wake_morning = midnight_today - timedelta(days=days_ago)
        recent = days_ago <= 6
        bed_minutes = 15 + bed_noise * 55 if recent else -50 + bed_noise * 18   # minutes from midnight
        asleep = 6.05 + length_noise * 0.3 if recent else 7.4 + length_noise * 0.35
        bedtime = wake_morning + timedelta(minutes=bed_minutes)
        wake = bedtime + timedelta(hours=asleep + 0.45)    # time in bed includes brief awakenings
        if wake > now:
            continue                                       # last night isn't over yet
        nights.append(SleepNight(wake_morning.date(), bedtime, wake, asleep))
    return nights


def demo_intraday(metric_id: str, day, now: datetime) -> list[tuple[datetime, float]]:
    """Readings within one day, for the 'Day' chart."""
    start = datetime(day.year, day.month, day.day)
    end = min(start + timedelta(days=1), now)
    rng = SeededRandom(seed_for(metric_id) ^ day.toordinal())
    points = []
    if metric_id == "heart_rate":
        t = start
        while t < end:
            hour = (t - start).total_seconds() / 3600
            daily_rhythm = -9.0 if hour < 6.5 else math.sin((hour - 6.5) / 17 * math.pi) * 10
            points.append((t, 68 + daily_rhythm + rng.gaussian() * 3))
            t += timedelta(minutes=10)
    elif metric_id == "hrv":
        for hour in (2.3, 5.1, 9.8, 14.2, 20.6):
            if start + timedelta(hours=hour) < end:
                points.append((start + timedelta(hours=hour), 45 + rng.gaussian() * 9))
    elif metric_id == "breathing":
        for hour in (0.5, 1.5, 2.5, 3.5, 4.5, 5.5, 6.5):
            if start + timedelta(hours=hour) < end:
                points.append((start + timedelta(hours=hour), 14.6 + rng.gaussian() * 0.6))
    elif metric_id in ("steps", "distance"):
        factor = 1.0 if metric_id == "steps" else 0.00076
        for hour in range(24):
            if start + timedelta(hours=hour) >= end:
                break
            base = 650 + rng.gaussian() * 300 if 7 <= hour <= 21 else max(0, rng.gaussian() * 25)
            peak = 900 if hour in (8, 12, 18) else 0
            points.append((start + timedelta(hours=hour), max(0, base + peak) * factor))
    return points
