"""
/api/incidents — Fetch real-time traffic incidents in a bounding box
"""

from fastapi import APIRouter, Query
from models.schemas import IncidentsResponse, IncidentItem
from services import tomtom

router = APIRouter()

SEVERITY_MAP = {
    0: "UNKNOWN", 1: "MINOR", 2: "MODERATE", 3: "MAJOR", 4: "CRITICAL"
}

CATEGORY_MAP = {
    0: "UNKNOWN", 1: "ACCIDENT", 2: "FOG", 3: "DANGEROUS_CONDITIONS",
    4: "RAIN", 5: "ICE", 6: "JAM", 7: "LANE_CLOSED", 8: "ROAD_CLOSED",
    9: "ROAD_WORKS", 10: "WIND", 11: "FLOODING", 14: "BROKEN_DOWN_VEHICLE"
}


@router.get("", response_model=IncidentsResponse)
async def get_incidents(
    min_lat: float = Query(..., description="Bounding box min latitude"),
    min_lon: float = Query(..., description="Bounding box min longitude"),
    max_lat: float = Query(..., description="Bounding box max latitude"),
    max_lon: float = Query(..., description="Bounding box max longitude"),
):
    """
    Returns traffic incidents (accidents, closures, construction, congestion)
    within the given bounding box.
    """
    raw = await tomtom.fetch_incidents(min_lat, min_lon, max_lat, max_lon)

    incidents = []
    if raw:
        for item in raw.get("incidents", []):
            props = item.get("properties", {})
            geo = item.get("geometry", {}).get("coordinates", [0, 0])
            if isinstance(geo[0], list):
                geo = geo[0]  # take first point of LineString

            delay = props.get("delay", 0) or 0
            incidents.append(IncidentItem(
                type=CATEGORY_MAP.get(props.get("iconCategory", 0), "UNKNOWN"),
                severity=SEVERITY_MAP.get(props.get("magnitudeOfDelay", 0), "UNKNOWN"),
                description=f"{props.get('from', '')} → {props.get('to', '')}".strip(" →"),
                latitude=geo[1] if len(geo) > 1 else min_lat,
                longitude=geo[0],
                delay_minutes=round(delay / 60),
            ))
    else:
        # Mock fallback
        incidents = [
            IncidentItem(
                type="ROAD_WORKS",
                severity="MODERATE",
                description="Construction on Outer Ring Road near Marathahalli",
                latitude=(min_lat + max_lat) / 2,
                longitude=(min_lon + max_lon) / 2,
                delay_minutes=12,
            ),
            IncidentItem(
                type="ACCIDENT",
                severity="MINOR",
                description="Minor accident on Sarjapur Road near Iblur",
                latitude=min_lat + 0.02,
                longitude=min_lon + 0.03,
                delay_minutes=5,
            ),
        ]

    return IncidentsResponse(total=len(incidents), incidents=incidents)
