from pydantic import BaseModel
from typing import List, Optional

# ── Request models ──────────────────────────────────────────────

class RouteRequest(BaseModel):
    origin: str                  # "12.9716,77.5946" or "Koramangala, Bengaluru"
    destination: str             # "12.9698,77.7499" or "Whitefield, Bengaluru"
    travel_mode: str = "car"     # car | truck | pedestrian | bicycle
    max_alternatives: int = 3

class TrafficFlowRequest(BaseModel):
    latitude: float
    longitude: float
    radius_meters: int = 500

# ── Response models ─────────────────────────────────────────────

class TurnByTurnStep(BaseModel):
    instruction: str
    distance_m: float
    duration_sec: float
    street_name: Optional[str] = None

class RouteOption(BaseModel):
    route_id: int
    label: str
    distance_km: float
    eta_minutes: int
    traffic_delay_minutes: int
    traffic_ratio: float          # 0.0 - 1.0 (higher = more congested)
    congestion_level: str         # LOW | MODERATE | HIGH
    traffic_color: str            # green | amber | red
    steps: List[TurnByTurnStep]
    summary_polyline: Optional[str] = None
    live_camera_location: Optional[str] = None   # matched live-feed location name, if any
    live_camera_vehicles: Optional[int] = None    # vehicle count from that camera report
    avoided_because: Optional[str] = None          # set if this route matched a user's "avoid X" request

class RoutesResponse(BaseModel):
    origin: str
    destination: str
    routes: List[RouteOption]     # sorted best-first (lowest traffic_ratio)
    best_route_id: int
    generated_at: str

class TrafficFlowSegment(BaseModel):
    road_name: str
    current_speed_kmh: float
    free_flow_speed_kmh: float
    traffic_ratio: float          # current/freeflow — lower = more congested
    congestion_level: str
    coordinates: List[List[float]]

class TrafficFlowResponse(BaseModel):
    latitude: float
    longitude: float
    segments: List[TrafficFlowSegment]
    area_congestion_score: float  # 0–100, higher = worse

class IncidentItem(BaseModel):
    type: str          # ACCIDENT | ROAD_CLOSURE | CONSTRUCTION | CONGESTION
    severity: str      # MINOR | MAJOR | CRITICAL
    description: str
    latitude: float
    longitude: float
    delay_minutes: int

class IncidentsResponse(BaseModel):
    total: int
    incidents: List[IncidentItem]

# ── Live camera feed (from the YOLOv8 detector) ─────────────────

class CameraReport(BaseModel):
    location_name: str            # e.g. "Marathahalli Bridge" — matched against route step text
    total_vehicles: int
    weighted_density: float
    density_level: str            # LOW | MODERATE | HIGH
    traffic_ratio: float          # 0.0 - 1.0

class LiveFeedItem(BaseModel):
    location_name: str
    total_vehicles: int
    weighted_density: float
    density_level: str
    traffic_ratio: float
    reported_at: str
    age_seconds: float

class LiveFeedResponse(BaseModel):
    total: int
    reports: List[LiveFeedItem]
