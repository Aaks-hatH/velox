"""
Small "robust" statistics used by the analysis.

Robust means one extreme day cannot drag the result around. For example the median
of [10, 11, 9, 500] is 10.5, while the average would be 132.5.

Used by: analysis.py, assistant_local.py
"""

import math

# Multiplying the MAD by this makes it comparable to a standard deviation.
MAD_TO_SIGMA = 1.4826


def median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 0:
        return (ordered[middle - 1] + ordered[middle]) / 2
    return ordered[middle]


def mad(values: list[float]) -> float | None:
    """Median absolute deviation: the typical distance of a value from the median."""
    m = median(values)
    if m is None:
        return None
    return median([abs(v - m) for v in values])


def mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def standard_deviation(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    m = mean(values)
    variance = sum((v - m) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def theil_sen_slope(x: list[float], y: list[float]) -> float | None:
    """
    The median of the slopes between every pair of points.
    Like a straight-line fit, but a single odd point barely changes it.
    """
    if len(x) != len(y) or len(x) < 3:
        return None
    slopes = []
    for i in range(len(x)):
        for j in range(i + 1, len(x)):
            if x[j] != x[i]:
                slopes.append((y[j] - y[i]) / (x[j] - x[i]))
    return median(slopes)
