"""
Traffic Ratio Analyzer
Core logic: computes congestion ratio per route and per road segment.

Traffic Ratio = trafficDelayInSeconds / travelTimeInSeconds
  0.00 – 0.15  → LOW      (green)
  0.16 – 0.40  → MODERATE (amber)
  0.41+        → HIGH     (red)

Road Segment Ratio = currentSpeed / freeFlowSpeed
  0.75+        → FREE FLOW
  0.50 – 0.74  → SLOW
  < 0.50       → CONGESTED
"""

from datetime import datetime
from typing import List, Dict, Any
from models.schemas import RouteOption, TurnByTurnStep, TrafficFlowSegment


def classify_traffic(ratio: float) -> tuple[str, str]:
    """Return (congestion_level, color) based on delay ratio."""
    if ratio <= 0.15:
        return "LOW", "green"
    elif ratio <= 0.40:
        return "MODERATE", "amber"
    else:
        return "HIGH", "red"


def classify_road_segment(speed_ratio: float) -> str:
    if speed_ratio >= 0.75:
        return "FREE FLOW"
    elif speed_ratio >= 0.50:
        return "SLOW"
    else:
        return "CONGESTED"


def parse_tomtom_route(raw_route: Dict[str, Any], route_id: int) -> RouteOption:
    """Parse a single TomTom route object into our RouteOption schema."""
    summary = raw_route.get("summary", {})

    travel_time_sec = summary.get("travelTimeInSeconds", 1)
    delay_sec = summary.get("trafficDelayInSeconds", 0)
    length_m = summary.get("lengthInMeters", 0)

    traffic_ratio = round(delay_sec / max(travel_time_sec, 1), 3)
    congestion_level, traffic_color = classify_traffic(traffic_ratio)

    # Route label based on congestion
    labels = {
        "LOW": "Fastest & least traffic",
        "MODERATE": "Moderate traffic route",
        "HIGH": "Heavy traffic route",
    }
    label = labels[congestion_level]
    if route_id == 1:
        label = "Best route — " + label.split("—")[-1].strip() if "—" in label else label

    # Parse turn-by-turn steps
    steps: List[TurnByTurnStep] = []
    for leg in raw_route.get("legs", []):
        for point in leg.get("points", []):
            pass  # coordinates stored for polyline
        for instruction in leg.get("instructions", []):
            steps.append(TurnByTurnStep(
                instruction=instruction.get("message", "Continue"),
                distance_m=round(instruction.get("routeOffsetInMeters", 0), 1),
                duration_sec=round(instruction.get("travelTimeInSeconds", 0), 1),
                street_name=instruction.get("street", None),
            ))

    return RouteOption(
        route_id=route_id,
        label=label,
        distance_km=round(length_m / 1000, 1),
        eta_minutes=round(travel_time_sec / 60),
        traffic_delay_minutes=round(delay_sec / 60),
        traffic_ratio=traffic_ratio,
        congestion_level=congestion_level,
        traffic_color=traffic_color,
        steps=steps,
    )


def parse_tomtom_flow(flow_data: Dict[str, Any]) -> List[TrafficFlowSegment]:
    """Parse TomTom traffic flow response into segment list."""
    segments = []
    for segment in flow_data.get("flowSegmentData", []):
        current_speed = segment.get("currentSpeed", 0)
        free_flow = segment.get("freeFlowSpeed", 1)
        speed_ratio = round(current_speed / max(free_flow, 1), 3)

        segments.append(TrafficFlowSegment(
            road_name=segment.get("roadDescription", "Unknown road"),
            current_speed_kmh=round(current_speed, 1),
            free_flow_speed_kmh=round(free_flow, 1),
            traffic_ratio=speed_ratio,
            congestion_level=classify_road_segment(speed_ratio),
            coordinates=segment.get("coordinates", {}).get("coordinate", []),
        ))
    return segments


def compute_area_congestion_score(segments: List[TrafficFlowSegment]) -> float:
    """Aggregate congestion score 0–100 for an area (higher = worse)."""
    if not segments:
        return 0.0
    avg_ratio = sum(s.traffic_ratio for s in segments) / len(segments)
    # Invert: speed_ratio 1.0 = no congestion → score 0; 0.0 = full stop → score 100
    score = round((1 - avg_ratio) * 100, 1)
    return max(0.0, min(100.0, score))


def apply_avoid_preferences(routes: List["RouteOption"], avoid_terms: List[str]) -> List["RouteOption"]:
    """
    Mark routes that pass through something the driver asked to avoid
    (a road name, or a general term like "tolls"/"highways"), and push them
    to the bottom of the ranking rather than silently deleting them — a
    driver should still be able to see and pick an avoided route if every
    alternative is worse, just not have it recommended first.
    """
    if not avoid_terms:
        return routes

    terms = [t.lower().strip() for t in avoid_terms if t.strip()]
    for route in routes:
        haystack = " ".join(
            f"{s.instruction} {s.street_name or ''}" for s in route.steps
        ).lower()
        for term in terms:
            if term and term in haystack:
                route.avoided_because = term
                break
    return routes


def sort_routes_with_avoidance(routes: List["RouteOption"]) -> List["RouteOption"]:
    """Sort by traffic ratio, but any route matching an avoid-preference sinks
    below all non-avoided routes regardless of how good its ratio looks."""
    return sorted(routes, key=lambda r: (r.avoided_because is not None, r.traffic_ratio))


def sort_routes_by_traffic(routes: List[RouteOption]) -> List[RouteOption]:
    """Sort routes ascending by traffic_ratio (best first)."""
    return sorted(routes, key=lambda r: r.traffic_ratio)


def apply_live_camera_data(routes: List["RouteOption"], live_reports: List[dict]) -> List["RouteOption"]:
    """
    Blend live YOLOv8 camera reports into each route's traffic_ratio.

    For every route, check whether any of its turn-by-turn steps mention a
    location that currently has a live camera report (e.g. "Marathahalli
    Bridge"). If so, nudge the route's traffic_ratio toward what the camera
    actually observed — real, present-moment vehicle density — rather than
    trusting map-provider data alone. Blended 60/40 (camera/map) since a
    single camera sees one point on the route, not the whole path.
    """
    if not live_reports:
        return routes

    for route in routes:
        haystack = " ".join(
            f"{s.instruction} {s.street_name or ''}" for s in route.steps
        )
        match = None
        for report in live_reports:
            if report["location_name"].lower() in haystack.lower():
                if match is None or report["reported_at"] > match["reported_at"]:
                    match = report

        if match:
            blended_ratio = round(route.traffic_ratio * 0.4 + match["traffic_ratio"] * 0.6, 3)
            route.traffic_ratio = blended_ratio
            route.congestion_level, route.traffic_color = classify_traffic(blended_ratio)
            route.live_camera_location = match["location_name"]
            route.live_camera_vehicles = match["total_vehicles"]

    return routes


def generate_mock_routes(origin: str, destination: str) -> List[RouteOption]:
    """
    Fallback mock data when API key is not set.
    Useful for development and testing.
    """
    import random
    mock_routes = [
        RouteOption(
            route_id=1,
            label="Fastest & least traffic",
            distance_km=14.2,
            eta_minutes=28,
            traffic_delay_minutes=4,
            traffic_ratio=0.12,
            congestion_level="LOW",
            traffic_color="green",
            steps=[
                TurnByTurnStep(instruction="Head north on 100 Feet Rd", distance_m=1200, duration_sec=180),
                TurnByTurnStep(instruction="Turn right onto Outer Ring Road", distance_m=8500, duration_sec=900),
                TurnByTurnStep(instruction="Exit at Marathahalli Bridge", distance_m=2100, duration_sec=300),
                TurnByTurnStep(instruction="Continue straight to destination", distance_m=2400, duration_sec=360),
            ],
        ),
        RouteOption(
            route_id=2,
            label="Via Sarjapur Road",
            distance_km=17.8,
            eta_minutes=42,
            traffic_delay_minutes=14,
            traffic_ratio=0.33,
            congestion_level="MODERATE",
            traffic_color="amber",
            steps=[
                TurnByTurnStep(instruction="Take Sarjapur Road south", distance_m=3000, duration_sec=480),
                TurnByTurnStep(instruction="Merge onto ORR at Iblur junction", distance_m=9200, duration_sec=1100),
                TurnByTurnStep(instruction="Exit at Whitefield Main Road", distance_m=3600, duration_sec=540),
                TurnByTurnStep(instruction="Turn right at destination", distance_m=2000, duration_sec=300),
            ],
        ),
        RouteOption(
            route_id=3,
            label="Inner city route",
            distance_km=12.9,
            eta_minutes=58,
            traffic_delay_minutes=28,
            traffic_ratio=0.62,
            congestion_level="HIGH",
            traffic_color="red",
            steps=[
                TurnByTurnStep(instruction="Old Airport Road eastbound", distance_m=2500, duration_sec=600),
                TurnByTurnStep(instruction="Through Indiranagar (heavy congestion)", distance_m=3100, duration_sec=900),
                TurnByTurnStep(instruction="MG Road junction — expect delays", distance_m=4200, duration_sec=1200),
                TurnByTurnStep(instruction="Via Domlur — slow during peak hours", distance_m=3100, duration_sec=780),
            ],
        ),
    ]
    return mock_routes
