"""
Live Camera Feed
Holds recent vehicle-density reports pushed by the YOLOv8/YOLO26 detector
(traffic-ml/ml_api.py), keyed by a human-named location (e.g. a junction
or CCTV point). This is what closes the loop between the ML module and
the routing engine: a busy road detected by camera can nudge the traffic
ratio for any route that passes through it, instead of the two systems
running side by side without talking to each other.

Two separate windows are kept per location:
- The single "live" report (2-minute TTL) used by routing — a camera
  reading is only trusted to influence a route recommendation while it's
  genuinely fresh.
- A longer rolling history (30-minute window) used for trend forecasting —
  predicting whether a junction is getting worse needs more than one point.
"""

import time
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Dict, List, Optional

REPORT_TTL_SECONDS = 120       # a camera report is considered "live" for routing for 2 minutes
HISTORY_WINDOW_SECONDS = 1800  # keep up to 30 minutes of history per location for forecasting
HISTORY_MAX_POINTS = 60        # cap memory even if reports come in very frequently


class LiveFeed:
    def __init__(self):
        self._reports: Dict[str, dict] = {}
        self._history: Dict[str, deque] = {}
        self._lock = threading.Lock()

    def report(
        self,
        location_name: str,
        total_vehicles: int,
        weighted_density: float,
        density_level: str,
        traffic_ratio: float,
    ) -> None:
        key = location_name.strip().lower()
        now = time.time()
        with self._lock:
            self._reports[key] = {
                "location_name": location_name.strip(),
                "total_vehicles": total_vehicles,
                "weighted_density": weighted_density,
                "density_level": density_level,
                "traffic_ratio": traffic_ratio,
                "reported_at": now,
            }
            hist = self._history.setdefault(key, deque(maxlen=HISTORY_MAX_POINTS))
            hist.append({
                "location_name": location_name.strip(),
                "timestamp": now,
                "traffic_ratio": traffic_ratio,
                "weighted_density": weighted_density,
                "total_vehicles": total_vehicles,
            })

    def _prune(self) -> None:
        cutoff = time.time() - REPORT_TTL_SECONDS
        stale = [k for k, v in self._reports.items() if v["reported_at"] < cutoff]
        for k in stale:
            del self._reports[k]

    def _prune_history(self, key: str) -> None:
        cutoff = time.time() - HISTORY_WINDOW_SECONDS
        hist = self._history.get(key)
        if not hist:
            return
        while hist and hist[0]["timestamp"] < cutoff:
            hist.popleft()

    def all_reports(self) -> List[dict]:
        with self._lock:
            self._prune()
            now = time.time()
            return [
                {
                    **{k: v2 for k, v2 in v.items() if k != "reported_at"},
                    "reported_at": datetime.fromtimestamp(v["reported_at"], tz=timezone.utc).isoformat(),
                    "age_seconds": round(now - v["reported_at"], 1),
                }
                for v in self._reports.values()
            ]

    def match(self, text: str) -> Optional[dict]:
        """Return the freshest live report whose location name appears in `text`
        (e.g. a route step's instruction or street name), or None."""
        if not text:
            return None
        with self._lock:
            self._prune()
            needle = text.lower()
            best = None
            for v in self._reports.values():
                if v["location_name"].lower() in needle:
                    if best is None or v["reported_at"] > best["reported_at"]:
                        best = v
            return best

    def get_history(self, location_name: str) -> List[dict]:
        """Return the rolling history of readings for a location, oldest first."""
        key = location_name.strip().lower()
        with self._lock:
            self._prune_history(key)
            hist = self._history.get(key)
            return list(hist) if hist else []

    def known_locations(self) -> List[str]:
        """All location names with at least one history point in the current window."""
        with self._lock:
            names = []
            for key in list(self._history.keys()):
                self._prune_history(key)
                if self._history.get(key):
                    names.append(self._history[key][-1]["location_name"])
            return names


# Singleton shared across requests
live_feed = LiveFeed()
