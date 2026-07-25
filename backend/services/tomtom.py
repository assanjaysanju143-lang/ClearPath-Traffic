"""
TomTom API Client
Handles routing, traffic flow, and incident calls.
Docs: https://developer.tomtom.com/routing-api/documentation
"""

import httpx
from typing import Optional
from config import get_settings

BASE_ROUTING = "https://api.tomtom.com/routing/1/calculateRoute"
BASE_FLOW    = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"
BASE_INCIDENT = "https://api.tomtom.com/traffic/services/5/incidentDetails"

settings = get_settings()


async def fetch_routes(
    origin: str,
    destination: str,
    travel_mode: str = "car",
    max_alternatives: int = 3,
) -> Optional[dict]:
    """
    Fetch up to max_alternatives routes from TomTom Routing API.
    Returns raw JSON or None on failure.
    """
    url = f"{BASE_ROUTING}/{origin}:{destination}/json"
    params = {
        "key": settings.TOMTOM_API_KEY,
        "traffic": "true",
        "travelMode": travel_mode,
        "maxAlternatives": max_alternatives - 1,  # TomTom: 0 = 1 route, 2 = 3 routes
        "routeType": "fastest",
        "instructionsType": "text",
        "language": "en-GB",
        "computeTravelTimeFor": "all",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as e:
        print(f"[TomTom] Routing API error {e.response.status_code}: {e.response.text}")
        return None
    except Exception as e:
        print(f"[TomTom] Routing request failed: {e}")
        return None


async def fetch_traffic_flow(lat: float, lon: float) -> Optional[dict]:
    """
    Fetch traffic flow data for a road near given coordinates.
    Returns speed ratios and congestion info.
    """
    params = {
        "key": settings.TOMTOM_API_KEY,
        "point": f"{lat},{lon}",
        "unit": "KMPH",
        "openLr": "false",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(BASE_FLOW, params=params)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        print(f"[TomTom] Flow API failed: {e}")
        return None


async def fetch_incidents(
    min_lat: float, min_lon: float,
    max_lat: float, max_lon: float,
) -> Optional[dict]:
    """
    Fetch traffic incidents in a bounding box.
    """
    bbox = f"{min_lon},{min_lat},{max_lon},{max_lat}"
    params = {
        "key": settings.TOMTOM_API_KEY,
        "bbox": bbox,
        "fields": "{incidents{type,geometry,properties{id,iconCategory,magnitudeOfDelay,startTime,endTime,from,to,length,delay,roadNumbers,timeValidity,probabilityOfOccurrence,numberOfReports,lastReportTime,tmc{countryCode,tableNumber,tableVersion,direction,points{sequence,location}}}}}",
        "language": "en-GB",
        "categoryFilter": "0,1,2,3,4,5,6,7,8,9,10,11",
    }
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(BASE_INCIDENT, params=params)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        print(f"[TomTom] Incidents API failed: {e}")
        return None
