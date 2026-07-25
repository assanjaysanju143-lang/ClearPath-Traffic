"""
Tests for services/distributor.py — the core "divide vehicles across
routes" load-balancing logic.

The distributor delegates its congestion/load weighting choice to the
global bandit singleton. To test the load-balancing math itself in
isolation from the bandit's exploration randomness, these tests monkeypatch
`choose_arm` to return a fixed, known weighting.
"""

import pytest
from services.distributor import TrafficDistributor


SAMPLE_ROUTES = [
    {"route_id": 1, "label": "Fastest", "traffic_ratio": 0.10, "eta_minutes": 20},
    {"route_id": 2, "label": "Via Sarjapur", "traffic_ratio": 0.15, "eta_minutes": 25},
    {"route_id": 3, "label": "Inner city", "traffic_ratio": 0.60, "eta_minutes": 45},
]


@pytest.fixture
def fixed_weight_distributor(monkeypatch):
    """A distributor where the bandit always returns a fixed 0.7/0.3
    weighting (arm index 1) — isolates the load-balancing math from the
    bandit's own exploration behavior, which is tested separately."""
    d = TrafficDistributor()
    monkeypatch.setattr(
        "services.distributor.weight_bandit.choose_arm",
        lambda: (0.7, 0.3, 1),
    )
    return d


def test_first_assignment_picks_lowest_ratio_route(fixed_weight_distributor):
    result = fixed_weight_distributor.assign_route("user1", "A", "B", SAMPLE_ROUTES)
    # With no existing load, the lowest traffic_ratio route should win
    assert result["route"]["route_id"] == 1
    assert result["active_users_on_route"] == 1


def test_repeated_requests_spread_across_routes_instead_of_piling_on_one(fixed_weight_distributor):
    """The core claim of the whole project: sending the same request
    repeatedly should NOT always return the same route once load builds up."""
    assigned_ids = []
    for i in range(5):
        result = fixed_weight_distributor.assign_route(f"user{i}", "A", "B", SAMPLE_ROUTES)
        assigned_ids.append(result["route"]["route_id"])

    # Not everyone should end up on the same route
    assert len(set(assigned_ids)) > 1, "distributor sent every user down the same route"
    # The worst route (0.60 ratio) shouldn't be favored over the two good ones
    assert assigned_ids.count(3) <= 1


def test_release_route_decrements_active_users(fixed_weight_distributor):
    fixed_weight_distributor.assign_route("user1", "A", "B", SAMPLE_ROUTES)
    summary_before = fixed_weight_distributor.get_load_summary("A", "B")
    active_before = next(r["active_users"] for r in summary_before if r["route_id"] == 1)
    assert active_before == 1

    fixed_weight_distributor.release_route("user1")
    summary_after = fixed_weight_distributor.get_load_summary("A", "B")
    active_after = next(r["active_users"] for r in summary_after if r["route_id"] == 1)
    assert active_after == 0


def test_release_unknown_user_does_not_raise(fixed_weight_distributor):
    # Should be a safe no-op, not throw, since "just checking" lookups
    # release users that were never really tracked in some edge cases.
    fixed_weight_distributor.release_route("nobody_assigned_this_id")


def test_get_load_summary_includes_all_routes_even_with_zero_load(fixed_weight_distributor):
    fixed_weight_distributor.assign_route("user1", "A", "B", SAMPLE_ROUTES)
    summary = fixed_weight_distributor.get_load_summary("A", "B")
    assert len(summary) == 3
    route_ids = {r["route_id"] for r in summary}
    assert route_ids == {1, 2, 3}


def test_release_with_actual_minutes_feeds_bandit_reward(monkeypatch):
    d = TrafficDistributor()
    monkeypatch.setattr("services.distributor.weight_bandit.choose_arm", lambda: (0.7, 0.3, 1))

    captured = {}
    def fake_update(arm_index, reward):
        captured["arm_index"] = arm_index
        captured["reward"] = reward
    monkeypatch.setattr("services.distributor.weight_bandit.update", fake_update)

    d.assign_route("user1", "A", "B", SAMPLE_ROUTES)  # predicted_eta_minutes=20 (route 1)
    d.release_route("user1", actual_minutes=20)  # exact match -> reward should be 1.0

    assert captured["arm_index"] == 1
    assert captured["reward"] == pytest.approx(1.0, abs=1e-6)


def test_release_without_actual_minutes_does_not_feed_bandit(monkeypatch):
    """A manual 'just checking traffic' lookup (no real drive) shouldn't
    feed the bandit a reward at all, since there's no real outcome to
    learn from."""
    d = TrafficDistributor()
    monkeypatch.setattr("services.distributor.weight_bandit.choose_arm", lambda: (0.7, 0.3, 1))

    called = {"count": 0}
    def fake_update(arm_index, reward):
        called["count"] += 1
    monkeypatch.setattr("services.distributor.weight_bandit.update", fake_update)

    d.assign_route("user1", "A", "B", SAMPLE_ROUTES)
    d.release_route("user1")  # no actual_minutes

    assert called["count"] == 0
