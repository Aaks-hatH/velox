"""
Compares each person only with their OWN history.

For every measurement:
  1. "Recent"   = the last 7 complete days.
  2. "Baseline" = the 28 days before that ("your usual").
  3. Your usual value = baseline median; your usual variation = MAD x 1.4826.
  4. robust z = (recent median - baseline median) / usual variation.
  5. A change is reported only if ALL of these are true:
       - |z| >= 2   (>= 3 counts as "strong")
       - the change is at least the measurement's noise floor (metric.min_change)
       - at least half of the recent days are outside your usual range, in the same direction
         (so one odd day can't trigger a finding)
  6. Too little data -> no finding, and we say why.

No population "normal ranges" are used. The only fixed numbers are sensor limits
(to drop glitches) and noise floors.

Used by: app.py (to build the snapshot), assistant_local.py, assistant_ai.py
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from . import stats
from .metrics import Metric, format_change, format_value

RECENT_DAYS = 7
BASELINE_DAYS = 28
MIN_RECENT_DAYS = 4
MIN_BASELINE_DAYS = 14
NOTABLE_Z = 2.0
STRONG_Z = 3.0
SUSTAINED_FRACTION = 0.5


# ----------------------------------------------------------------------------
# Data types
# ----------------------------------------------------------------------------

@dataclass
class DailyValue:
    day: date
    value: float


@dataclass
class SleepNight:
    day: date             # the morning you woke up
    bedtime: datetime     # first time asleep
    wake_time: datetime   # last time asleep
    asleep_hours: float


@dataclass
class Series:
    """Daily history of one measurement, oldest first. Missing days are simply absent."""
    metric: Metric
    days: list[DailyValue]
    last_recorded: datetime | None = None
    is_demo: bool = False

    @property
    def latest(self) -> DailyValue | None:
        return self.days[-1] if self.days else None


@dataclass
class WindowStats:
    start: date          # first day in the window
    end: date            # day AFTER the last day (so windows never overlap)
    count: int           # days that have data
    expected_days: int   # calendar days in the window
    median: float
    spread: float        # MAD x 1.4826
    min: float
    max: float

    @property
    def last_day(self) -> date:
        return self.end - timedelta(days=1)


@dataclass
class DataQuality:
    observed_days: int
    expected_days: int
    longest_gap_days: int
    days_since_last_value: int | None
    discarded_readings: int
    issues: list[str]

    @property
    def coverage(self) -> float:
        return 0 if self.expected_days == 0 else self.observed_days / self.expected_days


@dataclass
class Finding:
    """A statistically unusual change, with every number needed to justify it."""
    metric: Metric
    baseline: WindowStats
    recent: WindowStats
    change: float            # recent median - baseline median
    percent_change: float
    robust_z: float
    direction: str           # "up" or "down"
    is_strong: bool
    days_beyond_range: int
    confidence: str          # "low", "moderate" or "high"
    evidence: list[str]
    limitations: list[str]

    @property
    def word(self) -> str:
        return "higher" if self.direction == "up" else "lower"

    @property
    def headline(self) -> str:
        return f"{self.metric.short_title} has been {self.word} than your usual"


@dataclass
class Assessment:
    """The result for one measurement: exactly one of unusual / typical / insufficient."""
    metric: Metric
    outcome: str                      # "unusual", "typical" or "insufficient"
    quality: DataQuality
    baseline: WindowStats | None = None
    recent: WindowStats | None = None
    trend_per_week: float | None = None
    finding: Finding | None = None
    reason: str = ""                  # filled in when outcome == "insufficient"


@dataclass
class SleepConsistency:
    nights: int
    bedtime_spread_minutes: float
    wake_spread_minutes: float
    previous_bedtime_spread_minutes: float | None
    average_bedtime: tuple[int, int]   # (hour, minute)
    average_wake: tuple[int, int]


@dataclass
class Snapshot:
    """Everything the pages and the assistant know at one moment."""
    series: dict[str, Series]
    assessments: dict[str, Assessment]
    sleep_nights: list[SleepNight]
    sleep_consistency: SleepConsistency | None
    generated_at: datetime
    is_demo: bool
    errors: dict[str, str] = field(default_factory=dict)

    @property
    def findings(self) -> list[Finding]:
        return [a.finding for a in self.assessments.values() if a.finding]


# ----------------------------------------------------------------------------
# Main entry points
# ----------------------------------------------------------------------------

def build_snapshot(series: dict[str, Series], nights: list[SleepNight], now: datetime, is_demo: bool) -> Snapshot:
    assessments = {metric_id: assess(s, now) for metric_id, s in series.items()}
    return Snapshot(series=series, assessments=assessments, sleep_nights=nights,
                    sleep_consistency=sleep_consistency(nights, now),
                    generated_at=now, is_demo=is_demo)


def assess(series: Series, now: datetime) -> Assessment:
    metric = series.metric
    baseline_start, recent_start, recent_end = analysis_windows(metric, now)

    # 1. Drop sensor glitches first, and remember how many.
    plausible = [d for d in series.days if metric.plausible_low <= d.value <= metric.plausible_high]
    discarded = len(series.days) - len(plausible)

    baseline_days = [d for d in plausible if baseline_start <= d.day < recent_start]
    recent_days = [d for d in plausible if recent_start <= d.day < recent_end]

    quality = data_quality(plausible, baseline_start, recent_end, discarded, now)
    baseline = window_stats(baseline_days, baseline_start, recent_start)
    recent = window_stats(recent_days, recent_start, recent_end)
    trend = trend_per_week(baseline_days + recent_days)

    def result(outcome: str, reason: str = "", finding: Finding | None = None) -> Assessment:
        return Assessment(metric, outcome, quality, baseline, recent, trend, finding, reason)

    # 2. Enough data?
    if not series.days:
        return result("insufficient", f"No {metric.title.lower()} data has been recorded yet.")
    if baseline is None or baseline.count < MIN_BASELINE_DAYS:
        return result("insufficient",
                      f"A personal baseline needs at least {MIN_BASELINE_DAYS} days of data in the "
                      f"{BASELINE_DAYS} days before this week; there are {len(baseline_days)}.")
    if recent is None or recent.count < MIN_RECENT_DAYS:
        return result("insufficient",
                      f"Only {len(recent_days)} of the last {RECENT_DAYS} days have data; at least "
                      f"{MIN_RECENT_DAYS} are needed to compare with your baseline.")

    # 3. How big is the change compared with your usual variation?
    # The spread never goes below half the noise floor, so a perfectly flat baseline
    # can't make a tiny change look enormous.
    spread = max(baseline.spread, metric.min_change / 2)
    change = recent.median - baseline.median
    z = change / spread
    direction = "up" if change >= 0 else "down"

    # 4. Was it sustained? Count recent days outside your usual range in that direction.
    if direction == "up":
        outside = sum(1 for d in recent_days if d.value > baseline.median + spread)
    else:
        outside = sum(1 for d in recent_days if d.value < baseline.median - spread)
    sustained = outside / len(recent_days) >= SUSTAINED_FRACTION

    if abs(z) < NOTABLE_Z or abs(change) < metric.min_change or not sustained:
        return result("typical")

    # 5. It's a finding: collect the evidence and the caveats.
    confidence = confidence_level(baseline, recent, quality)
    percent = 0 if baseline.median == 0 else change / abs(baseline.median) * 100
    word = "higher" if direction == "up" else "lower"
    evidence = [
        f"Last {recent.expected_days} days: median {format_value(metric, recent.median)} "
        f"({recent.count} of {recent.expected_days} days recorded).",
        f"Your previous {baseline.expected_days} days: median {format_value(metric, baseline.median)}, "
        f"usually within ±{format_value(metric, spread)}.",
        f"Difference: {format_change(metric, change)} ({'+' if percent >= 0 else '−'}{abs(percent):.0f}%), "
        f"about {abs(z):.1f}× your usual day-to-day variation.",
        f"{outside} of {recent.count} recent days were {word} than your usual range.",
    ]
    finding = Finding(metric, baseline, recent, change, percent, z, direction,
                      abs(z) >= STRONG_Z, outside, confidence, evidence,
                      limitations(metric, quality, confidence))
    return result("unusual", finding=finding)


def analysis_windows(metric: Metric, now: datetime) -> tuple[date, date, date]:
    """Returns (baseline_start, recent_start, recent_end). recent_end is exclusive."""
    today = now.date()
    # Step and distance totals for today aren't finished, so their last full day is yesterday.
    last_day = today - timedelta(days=1) if metric.today_is_partial else today
    recent_start = last_day - timedelta(days=RECENT_DAYS - 1)
    recent_end = last_day + timedelta(days=1)
    baseline_start = recent_start - timedelta(days=BASELINE_DAYS)
    return baseline_start, recent_start, recent_end


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------

def window_stats(days: list[DailyValue], start: date, end: date) -> WindowStats | None:
    values = [d.value for d in days]
    if not values:
        return None
    return WindowStats(start=start, end=end, count=len(values), expected_days=(end - start).days,
                       median=stats.median(values), spread=stats.mad(values) * stats.MAD_TO_SIGMA,
                       min=min(values), max=max(values))


def trend_per_week(days: list[DailyValue]) -> float | None:
    """Robust slope over the whole analysis window, in units per week."""
    if len(days) < 10:
        return None
    first = days[0].day
    x = [(d.day - first).days for d in days]
    y = [d.value for d in days]
    slope = stats.theil_sen_slope(x, y)
    return None if slope is None else slope * 7


def data_quality(values: list[DailyValue], start: date, end: date, discarded: int, now: datetime) -> DataQuality:
    in_window = [d for d in values if start <= d.day < end]
    expected = (end - start).days

    # Longest run of empty days inside the window.
    present = {d.day for d in in_window}
    longest_gap = current_gap = 0
    day = start
    while day < end:
        if day in present:
            current_gap = 0
        else:
            current_gap += 1
            longest_gap = max(longest_gap, current_gap)
        day += timedelta(days=1)

    days_since = (now.date() - values[-1].day).days if values else None

    issues = []
    if not values:
        issues.append("No readings found. This can mean your devices don't record it, Health access "
                      "wasn't granted, or the feature isn't supported.")
    else:
        if days_since is not None and days_since >= 3:
            issues.append(f"No new readings in the last {days_since} days.")
        if longest_gap >= 3:
            issues.append(f"The longest stretch without data was {longest_gap} days.")
        if expected > 0 and len(in_window) / expected < 0.6:
            issues.append(f"Only {len(in_window)} of {expected} days in the analysis window have data.")
    if discarded == 1:
        issues.append("1 reading was outside what the sensor can plausibly report and was ignored.")
    elif discarded > 1:
        issues.append(f"{discarded} readings were outside what the sensor can plausibly report and were ignored.")

    return DataQuality(len(in_window), expected, longest_gap, days_since, discarded, issues)


def confidence_level(baseline: WindowStats, recent: WindowStats, quality: DataQuality) -> str:
    if baseline.count >= 24 and recent.count >= 6 and quality.longest_gap_days < 3:
        return "high"
    if baseline.count >= 18 and recent.count >= 5:
        return "moderate"
    return "low"


def limitations(metric: Metric, quality: DataQuality, confidence: str) -> list[str]:
    notes = []
    if confidence == "low":
        notes.append("Based on a limited number of days, so this pattern may not hold.")
    notes.extend(quality.issues)
    if metric.is_activity:
        notes.append("Activity totals reflect how much you moved and whether you carried your devices.")
    else:
        notes.append("Wrist-based sensors can be affected by watch fit, movement, temperature, and device changes.")
    notes.append("This is a statistical comparison with your own history, not a medical assessment.")
    return notes


# ----------------------------------------------------------------------------
# Sleep schedule
# ----------------------------------------------------------------------------

def sleep_consistency(nights: list[SleepNight], now: datetime) -> SleepConsistency | None:
    """How much bed and wake times varied over the last 14 nights (vs the 14 before)."""
    today = now.date()
    start = today - timedelta(days=13)
    previous_start = today - timedelta(days=27)
    recent = [n for n in nights if start <= n.day <= today]
    previous = [n for n in nights if previous_start <= n.day < start]
    if len(recent) < 5:
        return None

    bed = [minutes_from_midnight(n.bedtime) for n in recent]
    wake = [minutes_from_midnight(n.wake_time) for n in recent]
    previous_spread = None
    if len(previous) >= 5:
        previous_spread = stats.standard_deviation([minutes_from_midnight(n.bedtime) for n in previous])

    return SleepConsistency(
        nights=len(recent),
        bedtime_spread_minutes=stats.standard_deviation(bed) or 0,
        wake_spread_minutes=stats.standard_deviation(wake) or 0,
        previous_bedtime_spread_minutes=previous_spread,
        average_bedtime=clock_from_minutes(stats.mean(bed)),
        average_wake=clock_from_minutes(stats.mean(wake)),
    )


def minutes_from_midnight(moment: datetime) -> float:
    """Evening times are negative, so 23:30 and 00:30 count as 60 minutes apart (not 23 hours)."""
    minutes = moment.hour * 60 + moment.minute
    if minutes >= 12 * 60:
        minutes -= 24 * 60
    return minutes


def clock_from_minutes(minutes: float) -> tuple[int, int]:
    m = round(minutes)
    if m < 0:
        m += 24 * 60
    return divmod(m, 60)
