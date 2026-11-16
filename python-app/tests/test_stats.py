from vitalsense import stats


def test_median_odd_and_even():
    assert stats.median([3, 1, 2]) == 2
    assert stats.median([4, 1, 3, 2]) == 2.5
    assert stats.median([]) is None


def test_mad_ignores_outlier():
    # One huge value barely moves the MAD, unlike the standard deviation.
    values = [10, 11, 9, 10, 10, 11, 9, 500]
    assert stats.mad(values) <= 1
    assert stats.standard_deviation(values) > 100


def test_theil_sen_recovers_slope_despite_outlier():
    x = list(range(20))
    y = [2 * v + 5 for v in x]
    y[7] = 400
    assert abs(stats.theil_sen_slope(x, y) - 2) < 0.01
