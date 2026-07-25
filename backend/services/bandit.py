"""
Weight Bandit — learns the distributor's congestion/load weighting instead
of trusting a hand-picked constant.

Why this exists: the original distributor scored routes as
    0.7 * congestion + 0.3 * load
where 0.7/0.3 was a number that looked reasonable in testing, not something
derived from outcomes. This module replaces that constant with an
epsilon-greedy multi-armed bandit: a small set of candidate weightings
("arms"), each tracking a running average reward, with the system mostly
picking the best-performing arm so far but still occasionally exploring
others so it can keep adapting.

Reward signal: when a real (GPS-tracked) navigation finishes, the frontend
reports how long the trip actually took. We compare that to the ETA that was
predicted at assignment time. A weighting arm that tends to produce
predictions matching reality gets reward close to 1; an arm that either
ignores congestion (routes end up slower than promised) or ignores load
(routes get overloaded and slow down in practice) drifts toward 0. This is
a proxy, not a perfect metric — it's explained as such in the README — but
it's a real, principled signal rather than an arbitrary constant.

This is intentionally simple (no persistence, no contextual features) so
it's easy to explain end-to-end: it's meant to demonstrate the *idea* of
learning a weighting from outcomes, not to be a production bandit library.
"""

import random
import threading
from dataclasses import dataclass, field
from typing import List, Tuple

# Candidate (congestion_weight, load_weight) pairs. Must each sum to 1.0.
ARMS: List[Tuple[float, float]] = [
    (0.9, 0.1),   # trust congestion data almost completely
    (0.7, 0.3),   # original hand-picked default
    (0.5, 0.5),   # split evenly
    (0.3, 0.7),   # aggressively spread load even onto busier routes
]

EPSILON = 0.15  # 15% of the time, explore a random arm instead of the current best


@dataclass
class ArmStats:
    pulls: int = 0
    total_reward: float = 0.0

    @property
    def average(self) -> float:
        return self.total_reward / self.pulls if self.pulls else 0.0


class WeightBandit:
    def __init__(self):
        self._stats = {i: ArmStats() for i in range(len(ARMS))}
        self._lock = threading.Lock()

    def choose_arm(self) -> Tuple[float, float, int]:
        """Return (congestion_weight, load_weight, arm_index)."""
        with self._lock:
            if random.random() < EPSILON:
                idx = random.randrange(len(ARMS))
            else:
                # Arms never pulled are treated as worth trying (optimistic init)
                # so the bandit doesn't get stuck on an early lucky arm.
                unseen = [i for i, s in self._stats.items() if s.pulls == 0]
                idx = unseen[0] if unseen else max(self._stats, key=lambda i: self._stats[i].average)
            w_congestion, w_load = ARMS[idx]
            return w_congestion, w_load, idx

    def update(self, arm_index: int, reward: float) -> None:
        """reward should be in [0, 1] — higher is better."""
        reward = max(0.0, min(1.0, reward))
        with self._lock:
            stats = self._stats[arm_index]
            stats.pulls += 1
            stats.total_reward += reward

    def stats(self) -> list:
        with self._lock:
            return [
                {
                    "arm_index": i,
                    "congestion_weight": ARMS[i][0],
                    "load_weight": ARMS[i][1],
                    "pulls": s.pulls,
                    "average_reward": round(s.average, 3),
                }
                for i, s in self._stats.items()
            ]


def eta_accuracy_reward(predicted_minutes: float, actual_minutes: float) -> float:
    """
    1.0 = actual travel time matched the prediction exactly.
    Drops toward 0 the further actual time strays from predicted, in either
    direction (much faster than predicted is also a sign the weighting/ETA
    combination wasn't well calibrated, not just a happy surprise).
    """
    if predicted_minutes <= 0:
        return 0.5  # no meaningful prediction to compare against
    error_ratio = abs(actual_minutes - predicted_minutes) / predicted_minutes
    return max(0.0, 1.0 - error_ratio)


# Singleton shared across requests
weight_bandit = WeightBandit()
