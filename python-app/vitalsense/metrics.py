"""
The eight measurements Velox Health understands.

Everything that is specific to one measurement (its name, unit, colour, how much
change is worth mentioning, how to format its numbers) lives here, so the rest of
the app can treat every measurement the same way.

Used by: almost every other file.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Metric:
    id: str                 # short name used in URLs and code, e.g. "resting_hr"
    title: str              # full name shown on screen
    short_title: str        # compact name for lists
    unit: str               # "bpm", "ms", ...
    color: str              # line colour in charts (hex)
    is_activity: bool       # steps/distance describe behaviour, not the body
    today_is_partial: bool  # totals (steps, distance) aren't finished until midnight
    min_change: float       # smallest change worth mentioning (a noise floor, not a medical limit)
    plausible_low: float    # readings outside these sensor limits are glitches and get dropped
    plausible_high: float
    decimals: int           # how many decimals to show
    about: str              # plain explanation shown on the detail page
    keywords: tuple         # words the assistant uses to recognise questions about it
    everyday_factors: str   # common, non-medical reasons this can change


# Order matters: the assistant checks keywords in this order, so "resting heart rate"
# and "heart rate variability" are matched before plain "heart rate".
ALL_METRICS = [
    Metric("resting_hr", "Resting Heart Rate", "Resting HR", "bpm", "#F07A6C", False, False, 3, 25, 200, 0,
           "Apple Watch estimates resting heart rate from readings taken while you are still. "
           "It is calculated roughly once a day.",
           ("resting heart", "resting hr", "rhr", "resting pulse"),
           "sleep, stress, caffeine, alcohol, hydration, heat, training load, or a passing illness"),
    Metric("hrv", "Heart Rate Variability", "HRV", "ms", "#D596C8", False, False, 6, 1, 300, 0,
           "Heart rate variability (SDNN) measures how much the time between heartbeats varies. "
           "Apple Watch takes HRV readings occasionally, so there are only a few per day.",
           ("hrv", "variability", "sdnn"),
           "sleep, stress, alcohol, training load, or a passing illness"),
    Metric("heart_rate", "Heart Rate (non-workout)", "Heart Rate", "bpm", "#EE8FA6", False, False, 4, 25, 250, 0,
           "Daily median of heart-rate readings that were not taken during a workout. "
           "Leaving workouts out keeps exercise from looking like a change.",
           ("heart rate", "heartrate", "pulse", "bpm"),
           "sleep, stress, caffeine, alcohol, hydration, heat, training load, or a passing illness"),
    Metric("breathing", "Respiratory Rate", "Breathing", "br/min", "#6CC9D6", False, False, 1, 4, 60, 1,
           "Breaths per minute, measured by Apple Watch while you sleep.",
           ("respiratory", "breathing", "breath"),
           "sleep position, altitude, room conditions, or a passing illness"),
    Metric("sleep", "Sleep Duration", "Sleep", "h", "#9AA7EC", False, False, 0.5, 0.25, 18, 1,
           "Total time asleep per night. Overlapping records from different devices are merged "
           "so time is not counted twice.",
           ("sleep", "slept", "bedtime", "asleep"),
           "schedule changes, travel, late evenings, stress, or caffeine"),
    Metric("wrist_temp", "Sleeping Wrist Temp", "Wrist Temp", "°C", "#D2AE8E", False, False, 0.3, 30, 42, 2,
           "Wrist temperature measured during sleep by Apple Watch Series 8, Ultra, or later. "
           "Values vary between people and are best compared with your own history.",
           ("temperature", "temp", "wrist"),
           "room temperature, bedding, alcohol, the menstrual cycle, or a passing illness"),
    Metric("steps", "Steps", "Steps", "steps", "#7FCB97", True, True, 1500, 0, 120_000, 0,
           "Total steps per day from iPhone and Apple Watch, as combined by the Health app.",
           ("step",),
           "routine, weather, workload, or leaving your phone or watch behind"),
    Metric("distance", "Walking + Running", "Distance", "km", "#B2CB7A", True, True, 1.0, 0, 150, 1,
           "Total walking and running distance per day.",
           ("distance", "walking", "running", "walked", "km"),
           "routine, weather, workload, or leaving your phone or watch behind"),
]

# Look up a metric by its id: METRICS["sleep"]
METRICS = {metric.id: metric for metric in ALL_METRICS}


def format_value(metric: Metric, value: float, include_unit: bool = True) -> str:
    """Turn a number into text, e.g. 61.6 -> "62 bpm", 6.28 -> "6 h 17 min"."""
    if metric.id == "sleep":
        return format_hours(value)
    if metric.decimals == 0:
        number = f"{round(value):,}"
    else:
        number = f"{value:.{metric.decimals}f}"
    return f"{number} {metric.unit}" if include_unit else number


def format_change(metric: Metric, delta: float) -> str:
    """A signed change, e.g. "+6 bpm" or "−1 h 23 min"."""
    if delta > 0:
        sign = "+"
    elif delta < 0:
        sign = "−"
    else:
        sign = "±"
    return sign + format_value(metric, abs(delta))


def format_hours(hours: float) -> str:
    total_minutes = round(hours * 60)
    h, m = divmod(total_minutes, 60)
    if h == 0:
        return f"{m} min"
    return f"{h} h" if m == 0 else f"{h} h {m} min"
