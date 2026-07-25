"""
Vehicle Detection Module — built on Ultralytics YOLO26 (Jan 2026 release).
Detects and counts vehicles in images/video frames.
Calculates traffic density ratio per lane/zone.

Model family is configurable (defaults to YOLO26, the current Ultralytics
flagship) so a version bump later is a one-line change, not a rewrite:
    VehicleDetector(model_family="yolo26")   # default — best accuracy/latency
    VehicleDetector(model_family="yolo11")   # older, still well-supported
    VehicleDetector(model_family="yolov8")   # legacy, kept for reference

Supports:
- Single image detection
- Video file processing
- Real-time webcam feed
- RTSP camera stream (CCTV)
"""

import cv2
import numpy as np
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from ultralytics import YOLO

# Vehicle class IDs in the COCO dataset — identical across YOLOv8/11/26,
# since they all train on the same 80-class COCO label set.
VEHICLE_CLASSES = {
    2:  "car",
    3:  "motorcycle",
    5:  "bus",
    7:  "truck",
    1:  "bicycle",
}

# Weight of each vehicle type for density calculation
# Heavy vehicles contribute more to congestion
VEHICLE_WEIGHTS = {
    "car":        1.0,
    "motorcycle": 0.5,
    "bicycle":    0.3,
    "bus":        2.5,
    "truck":      2.5,
}

# Traffic density thresholds (weighted vehicles per detection zone)
DENSITY_THRESHOLDS = {
    "LOW":      (0,   8),
    "MODERATE": (8,   18),
    "HIGH":     (18,  float("inf")),
}

COLORS = {
    "car":        (0, 230, 118),   # green
    "motorcycle": (0, 200, 255),   # cyan
    "bicycle":    (100, 200, 255), # light blue
    "bus":        (255, 171, 0),   # amber
    "truck":      (255, 61, 61),   # red
}


@dataclass
class DetectionResult:
    frame_id:         int
    total_vehicles:   int
    vehicle_counts:   dict
    weighted_density: float
    density_level:    str        # LOW | MODERATE | HIGH
    traffic_ratio:    float      # 0.0–1.0 normalized
    fps:              float
    annotated_frame:  Optional[np.ndarray] = field(default=None, repr=False)


class VehicleDetector:
    # Ultralytics changed its weight-file naming between generations:
    # YOLOv8 kept the "v" (yolov8n.pt), YOLO11/YOLO26 dropped it (yolo11n.pt).
    _FAMILY_FILENAME = {
        "yolo26": "yolo26{size}.pt",
        "yolo11": "yolo11{size}.pt",
        "yolov8": "yolov8{size}.pt",
    }

    def __init__(self, model_size: str = "n", confidence: float = 0.35, model_family: str = "yolo26"):
        """
        model_size: n (nano-fastest) | s (small) | m (medium) | l (large)
        confidence: detection confidence threshold
        model_family: yolo26 (default, current flagship) | yolo11 | yolov8
        """
        if model_family not in self._FAMILY_FILENAME:
            raise ValueError(f"Unknown model_family '{model_family}'. Use one of {list(self._FAMILY_FILENAME)}.")
        weights = self._FAMILY_FILENAME[model_family].format(size=model_size)
        print(f"[{model_family.upper()}] Loading model {weights} ...")
        self.model = YOLO(weights)  # auto-downloads on first run if not present locally
        self.model_family = model_family
        self.model_size = model_size
        self.confidence = confidence
        self.frame_id = 0
        print(f"[{model_family.upper()}] Model ready.")

    def detect_frame(self, frame: np.ndarray, zone: Optional[list] = None) -> DetectionResult:
        """
        Detect vehicles in a single frame.
        zone: optional polygon [[x1,y1],[x2,y2],...] to restrict detection area
        """
        self.frame_id += 1
        h, w = frame.shape[:2]

        # Run inference
        results = self.model(frame, conf=self.confidence, verbose=False)[0]

        vehicle_counts = {v: 0 for v in VEHICLE_CLASSES.values()}
        boxes_to_draw = []

        for box in results.boxes:
            cls_id = int(box.cls[0])
            if cls_id not in VEHICLE_CLASSES:
                continue

            x1, y1, x2, y2 = map(int, box.xyxy[0])
            conf = float(box.conf[0])
            label = VEHICLE_CLASSES[cls_id]

            # Zone filter — only count vehicles inside the zone polygon
            if zone:
                cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
                poly = np.array(zone, dtype=np.float32)
                if cv2.pointPolygonTest(poly, (cx, cy), False) < 0:
                    continue

            vehicle_counts[label] += 1
            boxes_to_draw.append((x1, y1, x2, y2, label, conf))

        total = sum(vehicle_counts.values())
        weighted = sum(
            vehicle_counts[v] * VEHICLE_WEIGHTS[v]
            for v in vehicle_counts
        )

        # Normalize traffic ratio to 0–1 (cap at 30 weighted vehicles = fully congested)
        traffic_ratio = min(weighted / 30.0, 1.0)
        density_level = self._classify_density(weighted)

        # Draw annotations
        annotated = self._draw_annotations(
            frame.copy(), boxes_to_draw, total, weighted, density_level, zone
        )

        return DetectionResult(
            frame_id=self.frame_id,
            total_vehicles=total,
            vehicle_counts={k: v for k, v in vehicle_counts.items() if v > 0},
            weighted_density=round(weighted, 2),
            density_level=density_level,
            traffic_ratio=round(traffic_ratio, 3),
            fps=0.0,
            annotated_frame=annotated,
        )

    def _classify_density(self, weighted: float) -> str:
        for level, (lo, hi) in DENSITY_THRESHOLDS.items():
            if lo <= weighted < hi:
                return level
        return "HIGH"

    def _draw_annotations(self, frame, boxes, total, weighted, level, zone):
        h, w = frame.shape[:2]

        # Draw zone polygon
        if zone:
            poly = np.array(zone, dtype=np.int32)
            cv2.polylines(frame, [poly], True, (255, 255, 255, 80), 2)
            overlay = frame.copy()
            cv2.fillPoly(overlay, [poly], (255, 255, 255))
            cv2.addWeighted(overlay, 0.06, frame, 0.94, 0, frame)

        # Draw bounding boxes
        for (x1, y1, x2, y2, label, conf) in boxes:
            color = COLORS.get(label, (200, 200, 200))
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            tag = f"{label} {conf:.0%}"
            (tw, th), _ = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
            cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 6, y1), color, -1)
            cv2.putText(frame, tag, (x1 + 3, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1, cv2.LINE_AA)

        # HUD overlay
        level_colors = {"LOW": (0, 230, 118), "MODERATE": (255, 171, 0), "HIGH": (255, 61, 61)}
        hud_color = level_colors.get(level, (200, 200, 200))

        cv2.rectangle(frame, (0, 0), (280, 110), (0, 0, 0), -1)
        cv2.rectangle(frame, (0, 0), (280, 110), hud_color, 1)

        cv2.putText(frame, "CLEARPATH DETECTOR", (10, 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, hud_color, 1, cv2.LINE_AA)
        cv2.putText(frame, f"Vehicles: {total}", (10, 45),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(frame, f"Density:  {weighted:.1f}", (10, 68),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(frame, f"Level:    {level}", (10, 91),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, hud_color, 1, cv2.LINE_AA)

        return frame
