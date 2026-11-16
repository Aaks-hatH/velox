"""Checks the Apple Health export reader with a tiny hand-written export file."""

import io
import zipfile
from datetime import datetime

from conftest import NOW
from vitalsense.health_export import load_export, merge_intervals

RECORD = '<Record type="{t}" sourceName="{s}" unit="{u}" startDate="{d} 07:00:00 +0000" endDate="{d} 07:01:00 +0000" value="{v}"/>'


def make_export(days: int = 40) -> bytes:
    rows = []
    for i in range(days):
        d = NOW.date().toordinal() - i
        day = datetime.fromordinal(d).strftime("%Y-%m-%d")
        rows.append(RECORD.format(t="HKQuantityTypeIdentifierRestingHeartRate", s="Watch", u="count/min", d=day, v=60))
        # The same steps counted by iPhone and Watch: only the larger total should be kept.
        rows.append(RECORD.format(t="HKQuantityTypeIdentifierStepCount", s="iPhone", u="count", d=day, v=8000))
        rows.append(RECORD.format(t="HKQuantityTypeIdentifierStepCount", s="Watch", u="count", d=day, v=9000))
    xml = '<?xml version="1.0"?><HealthData>' + "".join(rows) + "</HealthData>"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("apple_health_export/export.xml", xml)
    buffer.seek(0)
    return buffer


def test_reads_zip_export_and_avoids_double_counting_steps():
    snapshot = load_export(make_export(), NOW, ["resting_hr", "steps"])
    assert snapshot.is_demo is False
    assert snapshot.assessments["resting_hr"].outcome == "typical"
    steps = snapshot.series["steps"].days
    assert len(steps) >= 30
    assert all(d.value == 9000 for d in steps)


def test_sleep_intervals_are_merged():
    t0 = datetime(2026, 3, 14, 23, 0)
    hour = 3600
    from datetime import timedelta
    merged = merge_intervals([
        (t0, t0 + timedelta(seconds=hour)),
        (t0 + timedelta(seconds=1800), t0 + timedelta(seconds=1800 + hour)),   # overlaps (other device)
        (t0 + timedelta(hours=3), t0 + timedelta(hours=3, minutes=10)),
    ])
    assert len(merged) == 2
    assert (merged[0][1] - merged[0][0]).total_seconds() == 5400
