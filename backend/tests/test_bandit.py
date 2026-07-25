"""
Tests for services/bandit.py — the multi-armed bandit that learns route-
scoring weights instead of trusting a hand-picked constant.
"""

import random
import pytest
from services.bandit import WeightBandit, eta_accuracy_reward, ARMS


def test_choose_arm_returns_valid_weights():
    b = WeightBandit()
    w_congestion, w_load, idx = b.choose_arm()
    assert 0 <= idx < len(ARMS)
    assert (w_congestion, w_load) == ARMS[idx]
    assert abs(w_congestion + w_load - 1.0) < 1e-9


def test_all_arms_get_tried_eventually():
    """With optimistic initialization, every arm should get pulled at least
    once fairly quickly — otherwise a lucky first result could get "stuck
    on" forever. Uses a fixed seed and generous call budget since the 15%
    random-exploration branch means arm discovery order isn't strictly
    deterministic call-by-call."""
    random.seed(42)
    b = WeightBandit()
    seen = set()
    for _ in range(30):  # generous budget — 4 arms, should all appear well within this
        _, _, idx = b.choose_arm()
        b.update(idx, 0.5)
        seen.add(idx)
    assert seen == set(range(len(ARMS)))


def test_update_clamps_reward_to_valid_range():
    b = WeightBandit()
    b.update(0, 5.0)   # way above 1.0
    b.update(1, -3.0)  # below 0.0
    stats = {s["arm_index"]: s for s in b.stats()}
    assert stats[0]["average_reward"] == 1.0
    assert stats[1]["average_reward"] == 0.0


def test_stats_reflects_pulls_and_average():
    b = WeightBandit()
    b.update(2, 0.8)
    b.update(2, 0.6)
    stats = {s["arm_index"]: s for s in b.stats()}
    assert stats[2]["pulls"] == 2
    assert stats[2]["average_reward"] == pytest.approx(0.7, abs=1e-6)


def test_bandit_converges_to_genuinely_best_arm():
    """The core claim: given enough trials, the bandit should favor the arm
    with the highest true reward far more than the others."""
    random.seed(7)
    b = WeightBandit()
    true_quality = {0: 0.55, 1: 0.95, 2: 0.65, 3: 0.45}

    for _ in range(500):
        _, _, idx = b.choose_arm()
        reward = max(0, min(1, true_quality[idx] + random.uniform(-0.1, 0.1)))
        b.update(idx, reward)

    stats = {s["arm_index"]: s for s in b.stats()}
    # Arm 1 is the genuinely best — it should dominate the pull count.
    assert stats[1]["pulls"] > 300, "bandit failed to converge to the best-performing arm"
    # And its learned average should be close to its true quality.
    assert stats[1]["average_reward"] == pytest.approx(0.95, abs=0.05)


class TestEtaAccuracyReward:
    def test_perfect_prediction_gives_full_reward(self):
        assert eta_accuracy_reward(30, 30) == 1.0

    def test_reward_drops_with_error(self):
        assert eta_accuracy_reward(30, 45) < eta_accuracy_reward(30, 33)

    def test_reward_never_negative(self):
        # actual time wildly different from predicted should floor at 0, not go negative
        assert eta_accuracy_reward(10, 1000) == 0.0

    def test_zero_predicted_time_handled_gracefully(self):
        # shouldn't divide by zero or crash
        assert eta_accuracy_reward(0, 20) == 0.5
