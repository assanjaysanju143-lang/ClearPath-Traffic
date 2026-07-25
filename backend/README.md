# Traffic Route Backend — FastAPI

Smart traffic routing backend that detects congestion ratios and suggests the least-traffic route.

## Features
- Route suggestions sorted by traffic congestion ratio
- Real-time traffic flow per road segment
- Traffic incidents (accidents, road works, closures)
- In-memory caching to reduce API calls
- Mock data fallback for development (no API key needed)

## Project Structure

```
traffic-backend/
├── main.py                  # FastAPI app entry point
├── config.py                # Settings + env vars
├── requirements.txt
├── .env.example             # Copy to .env and fill keys
├── models/
│   └── schemas.py           # Pydantic request/response models
├── routes/
│   ├── directions.py        # GET /api/routes
│   ├── traffic.py           # GET /api/traffic/flow, /ratio
│   └── incidents.py         # GET /api/incidents
└── services/
    ├── tomtom.py            # TomTom API calls
    ├── geocoder.py          # Address → lat,lon
    ├── analyzer.py          # Traffic ratio calculation logic
    └── cache.py             # In-memory TTL cache
```

## Quick Start

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Set up API key
```bash
cp .env.example .env
# Edit .env and add your TomTom API key
# Free key at: https://developer.tomtom.com (2500 calls/day free)
```

### 3. Run the server
```bash
python main.py
# OR
uvicorn main:app --reload --port 8000
```

### 4. Open API docs
```
http://localhost:8000/docs
```

---

## API Endpoints

### GET /api/routes
Suggest least-congested routes between two points.

```
GET /api/routes?origin=Koramangala,Bengaluru&destination=Whitefield,Bengaluru
```

Response:
```json
{
  "origin": "Koramangala, Bengaluru",
  "destination": "Whitefield, Bengaluru",
  "best_route_id": 1,
  "routes": [
    {
      "route_id": 1,
      "label": "Fastest & least traffic",
      "distance_km": 14.2,
      "eta_minutes": 28,
      "traffic_delay_minutes": 4,
      "traffic_ratio": 0.12,
      "congestion_level": "LOW",
      "traffic_color": "green",
      "steps": [...]
    }
  ]
}
```

### GET /api/traffic/flow
Real-time traffic flow for a location.
```
GET /api/traffic/flow?lat=12.9716&lon=77.5946
```

### GET /api/traffic/ratio
Simple congestion score (0–100) for a point.
```
GET /api/traffic/ratio?lat=12.9716&lon=77.5946
```

### GET /api/incidents
Traffic incidents in a bounding box.
```
GET /api/incidents?min_lat=12.90&min_lon=77.55&max_lat=12.99&max_lon=77.75
```

---

## Traffic Ratio Logic

| Ratio | Level | Color |
|-------|-------|-------|
| 0.00–0.15 | LOW | green |
| 0.16–0.40 | MODERATE | amber |
| 0.41+ | HIGH | red |

`traffic_ratio = trafficDelayInSeconds / travelTimeInSeconds`

## Next Steps
- [ ] Connect React frontend to `/api/routes`
- [ ] Add YOLOv8 vehicle detection module
- [ ] Deploy with Docker on Railway/Render
