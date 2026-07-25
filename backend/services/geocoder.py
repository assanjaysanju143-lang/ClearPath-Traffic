"""
Geocoding Service
Converts place names / addresses → lat,lon coordinates using TomTom Search API.
Falls back to a built-in table of well-known Bengaluru localities (and a
deterministic jitter around the city center for anything unrecognized) so the
app keeps working end-to-end when TomTom is unreachable, rate-limited, or no
API key is configured yet — matching the "no API key needed for dev" promise
in the README.
"""

import hashlib
import httpx
from config import get_settings

BASE_GEOCODE = "https://api.tomtom.com/search/2/geocode"

settings = get_settings()

# Well-known Bengaluru localities so demos / offline dev never hit a dead end.
BENGALURU_PLACES: dict[str, tuple[float, float]] = {
    "koramangala": (12.9352, 77.6245),
    "whitefield": (12.9698, 77.7500),
    "indiranagar": (12.9784, 77.6408),
    "electronic city": (12.8452, 77.6602),
    "marathahalli": (12.9569, 77.7011),
    "hebbal": (13.0358, 77.5970),
    "jayanagar": (12.9308, 77.5838),
    "btm layout": (12.9166, 77.6101),
    "mg road": (12.9758, 77.6045),
    "bellandur": (12.9257, 77.6774),
    "sarjapur road": (12.9010, 77.6870),
    "hsr layout": (12.9121, 77.6446),
    "yeshwanthpur": (13.0284, 77.5540),
    "banashankari": (12.9250, 77.5665),
    "rajajinagar": (12.9915, 77.5527),
    "bengaluru": (12.9716, 77.5946),
    "bangalore": (12.9716, 77.5946),
}

CITY_CENTER = (12.9716, 77.5946)  # Bengaluru, used as jitter origin for unknown names


def _mock_coords(address: str) -> tuple[float, float]:
    """Deterministic pseudo-geocode: known locality lookup, else a small
    reproducible offset from the city center so repeat calls for the same
    unknown address always return the same point."""
    key = address.strip().lower()
    for name, coords in BENGALURU_PLACES.items():
        if name in key:
            return coords

    digest = hashlib.md5(key.encode()).hexdigest()
    lat_off = (int(digest[:4], 16) / 0xFFFF - 0.5) * 0.18   # ~±10km
    lon_off = (int(digest[4:8], 16) / 0xFFFF - 0.5) * 0.18
    return round(CITY_CENTER[0] + lat_off, 5), round(CITY_CENTER[1] + lon_off, 5)


async def geocode(address: str) -> tuple[float, float] | None:
    """
    Convert address string to (lat, lon).
    Tries TomTom first (if a real API key is configured); always falls back
    to the local mock table/jitter on any failure, so this practically never
    returns None.
    """
    # If already in "lat,lon" format, return directly
    parts = address.strip().split(",")
    if len(parts) == 2:
        try:
            return float(parts[0].strip()), float(parts[1].strip())
        except ValueError:
            pass

    if settings.TOMTOM_API_KEY and settings.TOMTOM_API_KEY != "YOUR_TOMTOM_API_KEY":
        url = f"{BASE_GEOCODE}/{address}.json"
        params = {
            "key": settings.TOMTOM_API_KEY,
            "limit": 1,
            "countrySet": "IN",  # Bias to India; remove for global
        }
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                results = data.get("results", [])
                if results:
                    pos = results[0]["position"]
                    return pos["lat"], pos["lon"]
        except Exception as e:
            print(f"[Geocode] TomTom failed for '{address}', using mock fallback: {e}")

    return _mock_coords(address)


def coords_to_string(lat: float, lon: float) -> str:
    """Format (lat, lon) → 'lat,lon' string for TomTom routing."""
    return f"{lat},{lon}"
