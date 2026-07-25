"""
Congestion Forecaster

Turns a location's rolling history of camera readings (from live_feed.py)
into a short-term trend prediction — is this junction getting better or
worse, and if it's worsening, roughly how long until it's genuinely
congested?

Deliberately simple: a least-squares linear fit over the recent window,
no external dependencies (no numpy/pandas — this is meant to be easy to
explain end-to-end, not a serious time-series model). It's honest about
its own limits: fewer than MIN_POINTS readings, or readings that don't
actually vary over time, return "insufficient_data" rather than a
confident-sounding guess.
"""

import time
from typing import List, Optional

MIN_POINTS = 3            # need at least this many readings to fit a trend
MIN_TIME_SPAN_SECONDS = 60  # readings must span at least this long — a few
                            # readings seconds apart produce a wildly
                            # overconfident slope when extrapolated per-minute
FORECAST_HORIZON_MIN = 15  # how far ahead to project
HIGH_THRESHOLD = 0.40      # matches analyzer.classify_traffic's HIGH boundary


def _linear_fit(xs: List[float], ys: List[float]) -> Optional[tuple]:
    """Least-squares slope/intercept for y = slope*x + intercept. Returns
    None if there's no meaningful spread in x (can't fit a line through a
    single point in time)."""
    n = len(xs)
    x_mean = sum(xs) / n
    y_mean = sum(ys) / n
    denom = sum((x - x_mean) ** 2 for x in xs)
    if denom == 0:
        return None
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / denom
    intercept = y_mean - slope * x_mean
    return slope, intercept


def forecast_location(history: List[dict]) -> dict:
    """
    history: list of {timestamp, traffic_ratio, ...} dicts, oldest first
    (as returned by live_feed.get_history()).
    """
    if len(history) < MIN_POINTS:
        return {
            "status": "insufficient_data",
            "reason": "not_enough_readings",
            "points_available": len(history),
            "points_needed": MIN_POINTS,
        }

    time_span = history[-1]["timestamp"] - history[0]["timestamp"]
    if time_span < MIN_TIME_SPAN_SECONDS:
        return {
            "status": "insufficient_data",
            "reason": "readings_too_close_together",
            "points_available": len(history),
            "time_span_seconds": round(time_span, 1),
            "time_span_needed_seconds": MIN_TIME_SPAN_SECONDS,
        }

    now = time.time()
    # x in minutes-ago (negative = past), so "now" is x=0 and the forecast
    # horizon is a positive x — makes the fit trivial to reason about.
    xs = [(-((now - h["timestamp"]) / 60.0)) for h in history]
    ys = [h["traffic_ratio"] for h in history]

    fit = _linear_fit(xs, ys)
    if fit is None:
        return {
            "status": "insufficient_data",
            "reason": "no_time_variance",
            "points_available": len(history),
            "points_needed": MIN_POINTS,
        }

    slope, intercept = fit  # slope = change in traffic_ratio per minute
    current_ratio = ys[-1]
    predicted_ratio = max(0.0, min(1.0, slope * FORECAST_HORIZON_MIN + intercept))

    trend = "worsening" if slope > 0.002 else ("improving" if slope < -0.002 else "steady")

    minutes_to_high = None
    if trend == "worsening" and current_ratio < HIGH_THRESHOLD:
        # Solve slope*x + intercept = HIGH_THRESHOLD for x (minutes from now)
        minutes_to_high = round((HIGH_THRESHOLD - intercept) / slope, 1)
        if minutes_to_high < 0 or minutes_to_high > 120:
            minutes_to_high = None  # outside a sane/useful prediction range

    return {
        "status": "ok",
        "points_available": len(history),
        "current_ratio": round(current_ratio, 3),
        "trend": trend,
        "slope_per_minute": round(slope, 4),
        "predicted_ratio_in_15min": round(predicted_ratio, 3),
        "minutes_until_high_congestion": minutes_to_high,
    }
