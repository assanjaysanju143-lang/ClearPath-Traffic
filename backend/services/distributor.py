"""
Smart Traffic Distributor
Tracks how many users are on each route and assigns
the least-loaded route to each new user.

Distribution logic:
- Keeps a count of active users per route
- New user → assigned route with fewest active users
- User marks arrival → removed from count
- Rebalances every 10 minutes automatically
"""

import time
import threading
from typing import Dict, List
from dataclasses import dataclass, field
from services.bandit import weight_bandit, eta_accuracy_reward


@dataclass
class RouteLoad:
    route_id: int
    label: str
    active_users: int = 0
    total_assigned: int = 0
    last_assigned: float = field(default_factory=time.time)


class TrafficDistributor:
    def __init__(self):
        # route_key -> RouteLoad
        # key = f"{origin_hash}:{dest_hash}"
        self._loads: Dict[str, List[RouteLoad]] = {}
        self._lock = threading.Lock()
        self._user_assignments: Dict[str, dict] = {}  # user_id -> assignment

        # Auto-cleanup thread
        t = threading.Thread(target=self._cleanup_loop, daemon=True)
        t.start()

    def _route_key(self, origin: str, destination: str) -> str:
        return f"{origin.lower().strip()}:{destination.lower().strip()}"

    def assign_route(
        self,
        user_id: str,
        origin: str,
        destination: str,
        routes: list,  # list of RouteOption dicts
    ) -> dict:
        """
        Assign the best route to a user based on:
        1. Traffic ratio (congestion)
        2. Current load (how many users already on this route)

        Returns the assigned route + reason string.
        """
        key = self._route_key(origin, destination)

        with self._lock:
            # Init route loads if first time this origin-dest pair
            if key not in self._loads:
                self._loads[key] = [
                    RouteLoad(route_id=r["route_id"], label=r["label"])
                    for r in routes
                ]

            loads = self._loads[key]

            # Let the bandit pick this request's congestion/load weighting
            # instead of trusting a fixed constant.
            w_congestion, w_load, arm_index = weight_bandit.choose_arm()

            # Score each route: traffic_ratio * w_congestion + load_ratio * w_load
            max_users = max((l.active_users for l in loads), default=1) or 1
            scores = []
            for i, route in enumerate(routes):
                load = next((l for l in loads if l.route_id == route["route_id"]), None)
                if not load:
                    load = RouteLoad(route_id=route["route_id"], label=route["label"])
                    loads.append(load)

                traffic_score = route.get("traffic_ratio", 0.5)
                load_score    = load.active_users / max(max_users, 1)
                combined      = (traffic_score * w_congestion) + (load_score * w_load)
                scores.append((combined, i, route, load))

            # Pick lowest combined score
            scores.sort(key=lambda x: x[0])
            _, _, best_route, best_load = scores[0]

            # Increment load
            best_load.active_users += 1
            best_load.total_assigned += 1
            best_load.last_assigned = time.time()

            # Save user assignment — including which bandit arm chose this
            # route and what ETA it predicted, so release_route() can later
            # score this arm once we know how the trip actually went.
            self._user_assignments[user_id] = {
                "key": key,
                "route_id": best_route["route_id"],
                "assigned_at": time.time(),
                "bandit_arm": arm_index,
                "predicted_eta_minutes": best_route.get("eta_minutes", 0),
            }

            # Build reason message
            reason = self._build_reason(best_route, best_load, scores)

            return {
                "route": best_route,
                "reason": reason,
                "active_users_on_route": best_load.active_users,
                "distribution_score": round(scores[0][0], 3),
            }

    def release_route(self, user_id: str, actual_minutes: float = None):
        """
        Call when user reaches destination or closes app.

        If `actual_minutes` is given (a real GPS-tracked trip finishing, not
        a manual traffic lookup), score the bandit arm that made this
        assignment based on how close the predicted ETA was to reality.
        """
        with self._lock:
            assignment = self._user_assignments.pop(user_id, None)
            if not assignment:
                return
            loads = self._loads.get(assignment["key"], [])
            for load in loads:
                if load.route_id == assignment["route_id"]:
                    load.active_users = max(0, load.active_users - 1)
                    break

            if actual_minutes is not None and "bandit_arm" in assignment:
                reward = eta_accuracy_reward(assignment["predicted_eta_minutes"], actual_minutes)
                weight_bandit.update(assignment["bandit_arm"], reward)

    def get_load_summary(self, origin: str, destination: str) -> list:
        key = self._route_key(origin, destination)
        with self._lock:
            loads = self._loads.get(key, [])
            return [
                {
                    "route_id": l.route_id,
                    "label": l.label,
                    "active_users": l.active_users,
                    "total_assigned": l.total_assigned,
                }
                for l in loads
            ]

    def _build_reason(self, route: dict, load: RouteLoad, scores: list) -> str:
        level = route.get("congestion_level", "LOW")
        delay = route.get("traffic_delay_minutes", 0)
        users = load.active_users

        reasons = []

        cam_location = route.get("live_camera_location")
        if cam_location:
            reasons.append(
                f"live camera at {cam_location} confirms current density ({route.get('live_camera_vehicles', 0)} vehicles)"
            )

        if level == "LOW":
            reasons.append("lightest traffic right now")
        elif level == "MODERATE":
            reasons.append("moderate traffic but faster alternatives are busier")
        else:
            reasons.append("all routes have heavy traffic — this is still best")

        if delay == 0:
            reasons.append("no delays expected")
        elif delay <= 5:
            reasons.append(f"only {delay} min delay")
        else:
            reasons.append(f"{delay} min delay — least among all options")

        if users <= 2:
            reasons.append("very few users on this route")
        elif users <= 5:
            reasons.append("balanced load across routes")

        return "Suggested because: " + ", ".join(reasons[:3]) + "."

    def _cleanup_loop(self):
        """Remove stale assignments every 10 minutes."""
        while True:
            time.sleep(600)
            cutoff = time.time() - 3600  # 1 hour
            with self._lock:
                stale = [
                    uid for uid, a in self._user_assignments.items()
                    if a["assigned_at"] < cutoff
                ]
                for uid in stale:
                    self.release_route(uid)


# Singleton instance shared across requests
distributor = TrafficDistributor()
