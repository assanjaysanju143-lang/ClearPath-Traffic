"""
ML Detection API Server
Runs on port 8001, called by the main backend on port 8000.
Accepts image uploads and returns vehicle detection results.
"""

import cv2
import numpy as np
import base64
import io
import httpx
from fastapi import FastAPI, File, UploadFile, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from detector import VehicleDetector

app = FastAPI(title="ClearPath ML Detection API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Main routing backend — camera reports get pushed here so the routing
# engine can factor real, present-moment vehicle counts into its decisions.
BACKEND_URL = "https://clearpath-traffic.onrender.com"

# Load model once at startup
detector = VehicleDetector(model_size="n", confidence=0.35)

# Shared async client (reused across requests instead of opening a new
# connection each time) so the backend push never blocks the event loop.
_http_client = httpx.AsyncClient(timeout=2.0)


async def _push_to_backend(location_name: str, result) -> bool:
    """Best-effort push of a detection result to the main backend's live
    feed. Never raises — if the backend is down, detection still works,
    it just won't influence routing this time."""
    if not location_name:
        return False
    try:
        await _http_client.post(
            f"{BACKEND_URL}/api/traffic/report",
            json={
                "location_name": location_name,
                "total_vehicles": result.total_vehicles,
                "weighted_density": result.weighted_density,
                "density_level": result.density_level,
                "traffic_ratio": result.traffic_ratio,
            },
        )
        return True
    except Exception as e:
        print(f"[ML API] Could not reach backend to report '{location_name}': {e}")
        return False


class DetectionResponse(BaseModel):
    total_vehicles: int
    vehicle_counts: dict
    weighted_density: float
    density_level: str
    traffic_ratio: float
    annotated_image_b64: Optional[str] = None
    reported_to_backend: bool = False


@app.get("/")
def root():
    return {"message": "ClearPath ML API running", "docs": "/docs"}


@app.post("/detect/image", response_model=DetectionResponse)
async def detect_image(
    file: UploadFile = File(...),
    return_image: bool = True,
    location_name: Optional[str] = Form(None),
):
    """
    Upload a road image → get vehicle counts + traffic ratio.
    Optionally returns annotated image as base64.
    If `location_name` is given (e.g. "Marathahalli Bridge"), the result is
    also pushed to the main backend's live feed so it can influence route
    scoring for any route passing through that location.
    """
    contents = await file.read()
    np_arr = np.frombuffer(contents, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if frame is None:
        raise HTTPException(status_code=400, detail="Could not decode image.")

    result = detector.detect_frame(frame)

    annotated_b64 = None
    if return_image and result.annotated_frame is not None:
        _, buf = cv2.imencode(".jpg", result.annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        annotated_b64 = base64.b64encode(buf).decode("utf-8")

    reported = await _push_to_backend(location_name, result)

    return DetectionResponse(
        total_vehicles=result.total_vehicles,
        vehicle_counts=result.vehicle_counts,
        weighted_density=result.weighted_density,
        density_level=result.density_level,
        traffic_ratio=result.traffic_ratio,
        annotated_image_b64=annotated_b64,
        reported_to_backend=reported,
    )


@app.post("/detect/base64", response_model=DetectionResponse)
async def detect_base64(payload: dict):
    """
    Accept base64-encoded image string → return detection results.
    Useful for browser webcam integration.
    payload: { "image": "<base64 string>", "return_image": true, "location_name": "Marathahalli Bridge" }
    If `location_name` is given, the result is also pushed to the main
    backend's live feed so it can influence route scoring.
    """
    b64 = payload.get("image", "")
    if not b64:
        raise HTTPException(status_code=400, detail="Missing 'image' field.")

    # Strip data URL prefix if present
    if "," in b64:
        b64 = b64.split(",")[1]

    img_bytes = base64.b64decode(b64)
    np_arr = np.frombuffer(img_bytes, np.uint8)
    frame = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)

    if frame is None:
        raise HTTPException(status_code=400, detail="Could not decode image.")

    result = detector.detect_frame(frame)

    annotated_b64 = None
    if payload.get("return_image", True) and result.annotated_frame is not None:
        _, buf = cv2.imencode(".jpg", result.annotated_frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        annotated_b64 = base64.b64encode(buf).decode("utf-8")

    reported = await _push_to_backend(payload.get("location_name"), result)

    return DetectionResponse(
        total_vehicles=result.total_vehicles,
        vehicle_counts=result.vehicle_counts,
        weighted_density=result.weighted_density,
        density_level=result.density_level,
        traffic_ratio=result.traffic_ratio,
        annotated_image_b64=annotated_b64,
        reported_to_backend=reported,
    )


@app.get("/status")
def status():
    return {
        "model": f"{detector.model_family}{detector.model_size}",
        "status": "ready",
        "vehicle_classes": ["car", "motorcycle", "bicycle", "bus", "truck"],
        "port": 8001,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("ml_api:app", host="0.0.0.0", port=8001, reload=False)
