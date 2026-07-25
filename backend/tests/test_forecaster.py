"""
Tests for services/forecaster.py — short-term congestion trend prediction
from a location's rolling reading history.
"""

import time
import pytest
from services.forecaster import forecast_location, MIN_POINTS, MIN_TIME_SPAN_SECONDS


def _history(ratios, spacing_seconds, now=None):
    """Build a fake history: ratios oldest-first, spacing_seconds apart."""
    now = now or time.time()
    n = len(ratios)
    return [
        {"timestamp": now - (n - 1 - i) * spacing_seconds, "traffic_ratio": r}
        for i, r in enumerate(ratios)
    ]


def test_insufficient_data_below_min_points():
    hist = _history([0.1, 0.2], spacing_seconds=60)  # only 2 points, need 3
    result = forecast_location(hist)
    assert result["status"] == "insufficient_data"
    assert result["reason"] == "not_enough_readings"


def test_insufficient_data_when_readings_too_close_together():
    """Regression test for a real bug found during manual testing: readings
    only a few seconds apart produced a wildly overconfident extrapolated
    slope. Must be rejected even with enough *points*, if they don't span
    enough *time*."""
    hist = _history([0.1, 0.15, 0.2, 0.25, 0.3], spacing_seconds=1)
    result = forecast_location(hist)
    assert result["status"] == "insufficient_data"
    assert result["reason"] == "readings_too_close_together"
    assert result["time_span_seconds"] < MIN_TIME_SPAN_SECONDS


def test_worsening_trend_detected():
    ratios = [0.05 + i * 0.02 for i in range(10)]
    hist = _history(ratios, spacing_seconds=60)
    result = forecast_location(hist)
    assert result["status"] == "ok"
    assert result["trend"] == "worsening"
    assert result["slope_per_minute"] > 0


def test_worsening_trend_predicts_time_to_high_congestion():
    ratios = [0.05 + i * 0.02 for i in range(10)]  # ends at 0.23, HIGH threshold is 0.40
    hist = _history(ratios, spacing_seconds=60)
    result = forecast_location(hist)
    assert result["minutes_until_high_congestion"] is not None
    assert result["minutes_until_high_congestion"] > 0


def test_improving_trend_detected():
    ratios = [0.6 - i * 0.03 for i in range(10)]
    hist = _history(ratios, spacing_seconds=60)
    result = forecast_location(hist)
    assert result["status"] == "ok"
    assert result["trend"] == "improving"
    assert result["minutes_until_high_congestion"] is None


def test_flat_trend_detected_as_steady():
    ratios = [0.3] * 10
    hist = _history(ratios, spacing_seconds=60)
    result = forecast_location(hist)
    assert result["status"] == "ok"
    assert result["trend"] == "steady"
    assert result["minutes_until_high_congestion"] is None


def test_already_high_and_worsening_gives_no_misleading_countdown():
    """If congestion is already past the HIGH threshold, a 'minutes until
    HIGH' countdown doesn't make sense — should be None, not negative/zero."""
    ratios = [0.5 + i * 0.02 for i in range(10)]  # starts already above 0.4
    hist = _history(ratios, spacing_seconds=60)
    result = forecast_location(hist)
    assert result["current_ratio"] >= 0.40
    assert result["minutes_until_high_congestion"] is None


def test_predicted_ratio_is_clamped_to_valid_range():
    ratios = [0.6 - i * 0.1 for i in range(6)]  # would mathematically go negative
    hist = _history(ratios, spacing_seconds=60)
    result = forecast_location(hist)
    assert 0.0 <= result["predicted_ratio_in_15min"] <= 1.0
