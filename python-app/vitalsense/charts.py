"""
Draws the charts as SVG (the picture format browsers understand) using plain Python.

An SVG line is just a list of points: "M x1 y1 L x2 y2 L x3 y3 ...". So drawing a chart
means converting each (day, value) into an (x, y) position inside a box and joining them.

Used by: app.py (Today sparklines, metric detail chart)
"""

from html import escape

from .analysis import DailyValue, WindowStats
from .metrics import Metric, format_value


def scale(value: float, low: float, high: float, start: float, end: float) -> float:
    """Map value from the range low..high onto start..end (e.g. bpm -> pixels)."""
    if high == low:
        return (start + end) / 2
    return start + (value - low) / (high - low) * (end - start)


def sparkline(days: list[DailyValue], color: str, width: int = 54, height: int = 26) -> str:
    """Tiny trend line for the Today list. The last point gets a dot."""
    if len(days) < 2:
        return ""
    values = [d.value for d in days]
    low, high = min(values), max(values)
    pad = 3
    points = []
    for i, value in enumerate(values):
        x = scale(i, 0, len(values) - 1, pad, width - pad)
        y = scale(value, low, high, height - pad, pad)    # SVG y grows downwards, so flip
        points.append((x, y))
    path = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in points)
    last_x, last_y = points[-1]
    return (f'<svg class="spark" viewBox="0 0 {width} {height}" width="{width}" height="{height}" aria-hidden="true">'
            f'<path d="{path}" pathLength="1" fill="none" stroke="{color}" stroke-width="1.6" '
            f'stroke-linecap="round" stroke-linejoin="round"/>'
            f'<circle cx="{last_x:.1f}" cy="{last_y:.1f}" r="2.2" fill="{color}"/></svg>')


def detail_chart(days: list[DailyValue], metric: Metric, baseline: WindowStats | None,
                 width: int = 340, height: int = 220) -> dict:
    """
    The big chart on a measurement's page. Bars for steps/distance, a line for the rest.
    The shaded band is "your usual range" (baseline median +/- spread).
    Returns the SVG plus the point positions, which app.js uses to show values on hover.
    """
    if not days:
        return {"svg": "", "points": []}

    left, right, top, bottom = 8, 44, 14, 24            # room for labels on the right and bottom
    plot_w, plot_h = width - left - right, height - top - bottom

    values = [d.value for d in days]
    low, high = min(values), max(values)
    if baseline:
        low = min(low, baseline.median - baseline.spread)
        high = max(high, baseline.median + baseline.spread)
    if metric.is_activity:
        low = 0                                          # bars should start at zero
    margin = (high - low) * 0.08 or 1
    low, high = (low if metric.is_activity else low - margin), high + margin

    def x_at(i: int) -> float:
        if len(days) == 1:
            return left + plot_w / 2
        return scale(i, 0, len(days) - 1, left, left + plot_w)

    def y_at(value: float) -> float:
        return scale(value, low, high, top + plot_h, top)

    parts = [f'<svg class="chart" viewBox="0 0 {width} {height}" role="img" '
             f'aria-label="{escape(metric.title)} chart, {len(days)} days">']

    # Horizontal guide lines with labels: bottom, middle, top.
    for fraction in (0, 0.5, 1):
        value = low + (high - low) * fraction
        y = y_at(value)
        parts.append(f'<line class="grid" x1="{left}" x2="{left + plot_w}" y1="{y:.1f}" y2="{y:.1f}"/>')
        parts.append(f'<text class="axis" x="{width - 4}" y="{y + 4:.1f}" text-anchor="end">'
                     f'{escape(format_value(metric, value, include_unit=False))}</text>')

    # "Your usual" band and its middle line.
    if baseline:
        y_top, y_bottom = y_at(baseline.median + baseline.spread), y_at(baseline.median - baseline.spread)
        parts.append(f'<rect class="band" x="{left}" y="{y_top:.1f}" width="{plot_w}" '
                     f'height="{y_bottom - y_top:.1f}" fill="{metric.color}"/>')
        y_mid = y_at(baseline.median)
        parts.append(f'<line class="usual" x1="{left}" x2="{left + plot_w}" y1="{y_mid:.1f}" y2="{y_mid:.1f}" '
                     f'stroke="{metric.color}"/>')

    points = []
    if metric.is_activity:
        bar_w = max(2, plot_w / len(days) * 0.62)
        for i, d in enumerate(days):
            x, y = x_at(i), y_at(d.value)
            parts.append(f'<rect class="bar" x="{x - bar_w / 2:.1f}" y="{y:.1f}" width="{bar_w:.1f}" '
                         f'height="{top + plot_h - y:.1f}" rx="2" fill="{metric.color}"/>')
            points.append((x, y, d))
    else:
        coords = [(x_at(i), y_at(d.value)) for i, d in enumerate(days)]
        path = "M " + " L ".join(f"{x:.1f} {y:.1f}" for x, y in coords)
        parts.append(f'<path class="line" d="{path}" pathLength="1" fill="none" stroke="{metric.color}" '
                     f'stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>')
        if len(days) <= 31:
            for x, y in coords:
                parts.append(f'<circle class="dot" cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="{metric.color}"/>')
        points = [(x, y, d) for (x, y), d in zip(coords, days)]

    # Date labels under the first and last day.
    parts.append(f'<text class="axis" x="{left}" y="{height - 6}">{days[0].day.strftime("%-d %b")}</text>')
    parts.append(f'<text class="axis" x="{left + plot_w}" y="{height - 6}" text-anchor="end">'
                 f'{days[-1].day.strftime("%-d %b")}</text>')
    # Marker moved by app.js when you hover or drag across the chart.
    parts.append(f'<line class="cursor" x1="0" x2="0" y1="{top}" y2="{top + plot_h}" visibility="hidden"/>')
    parts.append("</svg>")

    hover_points = [{"x": round(x / width, 4), "label": d.day.strftime("%a %-d %b"),
                     "value": format_value(metric, d.value)} for x, y, d in points]
    return {"svg": "".join(parts), "points": hover_points}
