# ClearPath — YOLO26 Vehicle Detection Module

Detects vehicles in images, videos, webcam, or RTSP streams.
Calculates real-time traffic density ratio per frame.

## Install

```powershell
cd traffic-ml
py -3.12 -m pip install -r requirements.txt
```

> First run auto-downloads yolo26n.pt (~5MB). Needs internet once.
> Older generations still work if you need them: `--family yolo11` or `--family yolov8`.

---

## Usage

### 1. Detect in an image
```powershell
py -3.12 run.py --image road.jpg
```
Saves `road_detected.jpg` with bounding boxes + HUD overlay.

### 2. Process a video
```powershell
py -3.12 run.py --video traffic.mp4
```
Press `Q` to quit, `S` to save snapshot.

### 3. Live webcam
```powershell
py -3.12 run.py --webcam
```

### 4. RTSP / CCTV stream
```powershell
py -3.12 run.py --rtsp rtsp://192.168.1.10:554/stream
```

### 5. Start as API server (connects to frontend)
```powershell
py -3.12 run.py --server
# Docs: http://localhost:8001/docs
```

---

## Model sizes

| Flag | Model | Speed | Accuracy |
|------|-------|-------|----------|
| `--model n` | YOLO26 Nano | Fastest | Good |
| `--model s` | YOLO26 Small | Fast | Better |
| `--model m` | YOLO26 Medium | Moderate | Best for CPU |
| `--model l` | YOLO26 Large | Slow | Highest |

Default is `n` (nano) — best for real-time on CPU.

---

## What it detects

| Class | Weight | Notes |
|-------|--------|-------|
| Car | 1.0 | Standard weight |
| Motorcycle | 0.5 | Half weight |
| Bicycle | 0.3 | Light weight |
| Bus | 2.5 | Heavy — high congestion impact |
| Truck | 2.5 | Heavy — high congestion impact |

## Traffic Ratio Formula

```
weighted_density = Σ (vehicle_count × vehicle_weight)
traffic_ratio    = min(weighted_density / 30, 1.0)

LOW      → weighted < 8
MODERATE → weighted 8–18
HIGH     → weighted > 18
```

---

## Add to Frontend

Copy `MLDetector.jsx` into `traffic-frontend/src/components/`
Then import it in `App.jsx`:

```jsx
import MLDetector from './components/MLDetector'

// Add inside sidebar, below route results:
<MLDetector />
```

Make sure the ML server is running on port 8001:
```powershell
py -3.12 run.py --server
```

---

## All 3 Services Together

| Terminal | Command | Port |
|----------|---------|------|
| 1 — Backend | `py -3.12 main.py` in traffic-backend | 8000 |
| 2 — Frontend | `npm run dev` in traffic-frontend | 3000 |
| 3 — ML API | `py -3.12 run.py --server` in traffic-ml | 8001 |
