"""
/api/traffic — Real-time traffic flow and congestion ratio for a location
"""

from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Query
from models.schemas import (
    TrafficFlowRequest, TrafficFlowResponse, TrafficFlowSegment,
    CameraReport, LiveFeedResponse, LiveFeedItem,
)
from services import tomtom, analyzer, cache
from services.live_feed import live_feed
from services.forecaster import forecast_location

router = APIRouter()


@router.get("/flow", response_model=TrafficFlowResponse)
async def get_traffic_flow(
    lat: float = Query(..., description="Latitude"),
    lon: float = Query(..., description="Longitude"),
):
    """
    Returns real-time traffic flow data for roads near the given coordinates.
    Includes current speed, free-flow speed, and congestion ratio per segment.

    Traffic ratio = currentSpeed / freeFlowSpeed
    - >= 0.75 → FREE FLOW
    - 0.50–0.74 → SLOW
    - < 0.50 → CONGESTED
    """

    cache_key = cache.flow_key(lat, lon)
    cached = cache.get(cache_key)
    if cached:
        return cached

    raw = await tomtom.fetch_traffic_flow(lat, lon)

    if raw:
        segments = analyzer.parse_tomtom_flow(raw)
    else:
        # Mock fallback
        segments = [
            TrafficFlowSegment(
                road_name="Outer Ring Road",
                current_speed_kmh=28.0,
                free_flow_speed_kmh=60.0,
                traffic_ratio=0.47,
                congestion_level="CONGESTED",
                coordinates=[[lat, lon], [lat + 0.01, lon + 0.01]],
            ),
            TrafficFlowSegment(
                road_name="Sarjapur Road",
                current_speed_kmh=45.0,
                free_flow_speed_kmh=60.0,
                traffic_ratio=0.75,
                congestion_level="FREE FLOW",
                coordinates=[[lat, lon], [lat - 0.01, lon + 0.005]],
            ),
        ]

    congestion_score = analyzer.compute_area_congestion_score(segments)

    response = TrafficFlowResponse(
        latitude=lat,
        longitude=lon,
        segments=segments,
        area_congestion_score=congestion_score,
    )

    cache.set(cache_key, response, ttl=30)
    return response


@router.get("/ratio")
async def get_traffic_ratio(
    lat: float = Query(...),
    lon: float = Query(...),
):
    """
    Returns a simple 0–100 congestion score for a location.
    0 = completely free, 100 = fully gridlocked.
    """
    flow = await get_traffic_flow(lat=lat, lon=lon)
    return {
        "latitude": lat,
        "longitude": lon,
        "congestion_score": flow.area_congestion_score,
        "level": (
            "LOW" if flow.area_congestion_score < 30 else
            "MODERATE" if flow.area_congestion_score < 60 else
            "HIGH"
        )
    }


@router.post("/report", response_model=LiveFeedResponse)
async def report_camera_detection(report: CameraReport):
    """
    Called by the YOLOv8 ML detector (traffic-ml/ml_api.py) after each
    detection. Feeds live vehicle-density readings into the routing engine —
    any route whose steps mention this location gets its traffic ratio
    nudged by what the camera actually sees, instead of relying on TomTom's
    data alone.
    """
    live_feed.report(
        location_name=report.location_name,
        total_vehicles=report.total_vehicles,
        weighted_density=report.weighted_density,
        density_level=report.density_level,
        traffic_ratio=report.traffic_ratio,
    )
    return LiveFeedResponse(
        total=len(live_feed.all_reports()),
        reports=[LiveFeedItem(**r) for r in live_feed.all_reports()],
    )


@router.get("/live", response_model=LiveFeedResponse)
async def get_live_feed():
    """Returns all currently-live camera reports (not yet expired)."""
    reports = live_feed.all_reports()
    return LiveFeedResponse(total=len(reports), reports=[LiveFeedItem(**r) for r in reports])


@router.get("/forecast")
async def get_forecast(location_name: str = Query(...)):
    """
    Short-term congestion trend for a camera location, built from its
    rolling history of readings (up to the last 30 minutes). Needs at least
    3 readings to fit a trend — with fewer, returns "insufficient_data"
    rather than a guess. See services/forecaster.py for the (deliberately
    simple, dependency-free) linear-trend method.
    """
    history = live_feed.get_history(location_name)
    result = forecast_location(history)
    result["location_name"] = location_name
    return result


@router.get("/forecast/locations")
async def get_forecastable_locations():
    """All location names with enough recent history to forecast — lets the
    frontend show a picker instead of requiring an exact name match."""
    return {"locations": live_feed.known_locations()}
