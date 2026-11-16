"""
Reads an Apple Health export, so you can use your real data in Velox Health.

How to get the file: iPhone Health app -> your profile picture -> Export All Health Data.
It produces export.zip, which contains export.xml: one <Record> line per reading.

This file turns those readings into one value per day:
  - resting HR, HRV, breathing, wrist temperature: average of the day's readings
  - heart rate: median of the day's readings, leaving out workouts
  - steps, distance: daily total (see note on duplicates below)
  - sleep: time asleep per night, with overlapping records merged

The file is read in one streaming pass (it can be very large) and nothing is saved.

Used by: app.py (the /upload route)
"""

import zipfile
from collections import defaultdict
from datetime import datetime, timedelta
from xml.etree import ElementTree

from . import stats
from .analysis import DailyValue, Series, SleepNight, Snapshot, build_snapshot
from .metrics import METRICS

HISTORY_DAYS = 90

# Apple's names for each reading type -> our metric ids.
QUANTITY_TYPES = {
    "HKQuantityTypeIdentifierRestingHeartRate": "resting_hr",
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv",
    "HKQuantityTypeIdentifierHeartRate": "heart_rate",
    "HKQuantityTypeIdentifierRespiratoryRate": "breathing",
    "HKQuantityTypeIdentifierAppleSleepingWristTemperature": "wrist_temp",
    "HKQuantityTypeIdentifierStepCount": "steps",
    "HKQuantityTypeIdentifierDistanceWalkingRunning": "distance",
}
SLEEP_TYPE = "HKCategoryTypeIdentifierSleepAnalysis"
ASLEEP_VALUES = {
    "HKCategoryValueSleepAnalysisAsleep",
    "HKCategoryValueSleepAnalysisAsleepUnspecified",
    "HKCategoryValueSleepAnalysisAsleepCore",
    "HKCategoryValueSleepAnalysisAsleepDeep",
    "HKCategoryValueSleepAnalysisAsleepREM",
}


class ExportError(Exception):
    """A problem with the uploaded file, worded for the person using the app."""


def parse_time(text: str) -> datetime:
    """'2026-03-14 07:12:00 +0100' -> local time without a timezone label."""
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S %z").astimezone().replace(tzinfo=None)


def load_export(file, now: datetime, metric_ids: list[str]) -> Snapshot:
    """`file` is the uploaded export.zip (or export.xml) as an open file object."""
    xml_file = open_xml(file)
    cutoff = now - timedelta(days=HISTORY_DAYS)

    readings = defaultdict(list)                       # metric id -> [(start, value)]
    totals = defaultdict(lambda: defaultdict(float))   # metric id -> {(day, source): total}
    workouts = []                                      # [(start, end)]
    sleep_intervals = []                               # [(start, end)]

    try:
        for _, element in ElementTree.iterparse(xml_file, events=("end",)):
            tag = element.tag
            if tag == "Record":
                read_record(element, cutoff, readings, totals, sleep_intervals)
            elif tag == "Workout":
                start, end = parse_time(element.get("startDate")), parse_time(element.get("endDate"))
                if end >= cutoff:
                    workouts.append((start, end))
            if tag in ("Record", "Workout"):
                element.clear()                        # free memory as we go
    except ElementTree.ParseError as error:
        raise ExportError("This doesn't look like an Apple Health export (the XML couldn't be read).") from error

    series = {}
    for metric_id in metric_ids:
        metric = METRICS[metric_id]
        if metric_id == "sleep":
            continue
        if metric_id in ("steps", "distance"):
            days = daily_totals(totals[metric_id])
        elif metric_id == "heart_rate":
            days = daily_values(remove_workouts(readings[metric_id], workouts), use_median=True)
        else:
            days = daily_values(readings[metric_id], use_median=False)
        last = max((start for start, _ in readings[metric_id]), default=None)
        series[metric_id] = Series(metric, days, last, is_demo=False)

    nights = sleep_nights(sleep_intervals)
    if "sleep" in metric_ids:
        days = [DailyValue(n.day, n.asleep_hours) for n in nights]
        series["sleep"] = Series(METRICS["sleep"], days, nights[-1].wake_time if nights else None, is_demo=False)

    return build_snapshot(series, nights, now, is_demo=False)


def open_xml(file):
    """Accepts export.zip or a bare export.xml."""
    if zipfile.is_zipfile(file):
        file.seek(0)
        archive = zipfile.ZipFile(file)
        names = [n for n in archive.namelist() if n.endswith("export.xml")]
        if not names:
            raise ExportError("The zip file doesn't contain export.xml. Use Health › Export All Health Data.")
        return archive.open(names[0])
    file.seek(0)
    return file


def read_record(element, cutoff, readings, totals, sleep_intervals) -> None:
    record_type = element.get("type")
    if record_type == SLEEP_TYPE:
        if element.get("value") in ASLEEP_VALUES:
            start, end = parse_time(element.get("startDate")), parse_time(element.get("endDate"))
            if end >= cutoff:
                sleep_intervals.append((start, end))
        return

    metric_id = QUANTITY_TYPES.get(record_type)
    if metric_id is None:
        return
    start = parse_time(element.get("startDate"))
    if start < cutoff:
        return
    try:
        value = float(element.get("value"))
    except (TypeError, ValueError):
        return
    unit = element.get("unit", "")
    if metric_id == "distance" and unit == "mi":
        value *= 1.609344
    if metric_id == "wrist_temp" and unit == "degF":
        value = (value - 32) / 1.8

    if metric_id in ("steps", "distance"):
        # iPhone and Apple Watch both count steps. The Health app removes the overlap, but the
        # export contains both. A simple, safe rule: per day, keep the device with the larger total.
        totals[metric_id][(start.date(), element.get("sourceName", ""))] += value
    else:
        readings[metric_id].append((start, value))


def daily_values(readings: list[tuple[datetime, float]], use_median: bool) -> list[DailyValue]:
    by_day = defaultdict(list)
    for start, value in readings:
        by_day[start.date()].append(value)
    combine = stats.median if use_median else stats.mean
    return [DailyValue(day, combine(values)) for day, values in sorted(by_day.items())]


def daily_totals(totals: dict) -> list[DailyValue]:
    best = {}
    for (day, _source), total in totals.items():
        best[day] = max(best.get(day, 0), total)
    return [DailyValue(day, total) for day, total in sorted(best.items())]


def remove_workouts(readings, workouts):
    """Leave out heart-rate readings taken during a workout."""
    return [(t, v) for t, v in readings if not any(start <= t <= end for start, end in workouts)]


def merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    """Join overlapping sleep records (e.g. from iPhone and Watch) so time isn't counted twice."""
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def sleep_nights(intervals) -> list[SleepNight]:
    """Group sleep into nights. Sleep starting after 6 pm belongs to the next morning."""
    by_night = defaultdict(list)
    for start, end in merge_intervals(intervals):
        by_night[(start + timedelta(hours=6)).date()].append((start, end))
    nights = []
    for day, parts in sorted(by_night.items()):
        hours = sum((end - start).total_seconds() for start, end in parts) / 3600
        nights.append(SleepNight(day, parts[0][0], parts[-1][1], hours))
    return nights
