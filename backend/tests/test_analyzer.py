"""
Tests for services/analyzer.py — congestion classification, avoid-preference
handling, live camera data blending, and the mock-route fallback.
"""

import pytest
from services import analyzer
from services.analyzer import RouteOption, TurnByTurnStep


def make_route(route_id, ratio, instructions):
    level, color = analyzer.classify_traffic(ratio)
    return RouteOption(
        route_id=route_id,
        label=f"Route {route_id}",
        distance_km=10.0,
        eta_minutes=20,
        traffic_delay_minutes=5,
        traffic_ratio=ratio,
        congestion_level=level,
        traffic_color=color,
        steps=[TurnByTurnStep(instruction=i, distance_m=100, duration_sec=60, street_name=None) for i in instructions],
    )


class TestClassifyTraffic:
    def test_low_boundary(self):
        assert analyzer.classify_traffic(0.15) == ("LOW", "green")

    def test_moderate_boundary(self):
        assert analyzer.classify_traffic(0.40) == ("MODERATE", "amber")

    def test_high_above_boundary(self):
        assert analyzer.classify_traffic(0.41) == ("HIGH", "red")

    def test_zero_is_low(self):
        assert analyzer.classify_traffic(0.0)[0] == "LOW"


class TestAvoidPreferences:
    def test_matching_route_gets_marked(self):
        routes = [make_route(1, 0.1, ["Turn onto Sarjapur Road"])]
        result = analyzer.apply_avoid_preferences(routes, ["sarjapur road"])
        assert result[0].avoided_because == "sarjapur road"

    def test_non_matching_route_unaffected(self):
        routes = [make_route(1, 0.1, ["Turn onto MG Road"])]
        result = analyzer.apply_avoid_preferences(routes, ["sarjapur road"])
        assert result[0].avoided_because is None

    def test_empty_avoid_list_is_a_noop(self):
        routes = [make_route(1, 0.1, ["Turn onto MG Road"])]
        result = analyzer.apply_avoid_preferences(routes, [])
        assert result[0].avoided_because is None

    def test_avoided_route_sinks_below_non_avoided_regardless_of_ratio(self):
        """The key behavioral guarantee: even a much better (lower-ratio)
        route should rank below a worse one if it matches an avoid term."""
        good_but_avoided = make_route(1, 0.05, ["Via Sarjapur Road"])
        worse_but_fine   = make_route(2, 0.35, ["Via MG Road"])
        routes = [good_but_avoided, worse_but_fine]
        marked = analyzer.apply_avoid_preferences(routes, ["sarjapur road"])
        sorted_routes = analyzer.sort_routes_with_avoidance(marked)
        assert sorted_routes[0].route_id == 2  # the non-avoided one comes first
        assert sorted_routes[1].route_id == 1  # avoided one sinks, but is still present


class TestLiveCameraBlending:
    def test_matching_route_gets_boosted_and_marked(self):
        route = make_route(1, 0.12, ["Turn right onto Outer Ring Road"])
        reports = [{
            "location_name": "Outer Ring Road", "traffic_ratio": 0.9,
            "total_vehicles": 50, "reported_at": "2026-01-01T00:00:00+00:00",
        }]
        result = analyzer.apply_live_camera_data([route], reports)
        assert result[0].live_camera_location == "Outer Ring Road"
        assert result[0].live_camera_vehicles == 50
        # Blended 0.4*0.12 + 0.6*0.9 = 0.588
        assert result[0].traffic_ratio == pytest.approx(0.588, abs=0.001)
        assert result[0].congestion_level == "HIGH"

    def test_non_matching_route_unaffected(self):
        route = make_route(1, 0.12, ["Turn right onto MG Road"])
        reports = [{
            "location_name": "Outer Ring Road", "traffic_ratio": 0.9,
            "total_vehicles": 50, "reported_at": "2026-01-01T00:00:00+00:00",
        }]
        result = analyzer.apply_live_camera_data([route], reports)
        assert result[0].live_camera_location is None
        assert result[0].traffic_ratio == 0.12

    def test_empty_reports_is_a_noop(self):
        route = make_route(1, 0.12, ["Turn right onto Outer Ring Road"])
        result = analyzer.apply_live_camera_data([route], [])
        assert result[0].live_camera_location is None
        assert result[0].traffic_ratio == 0.12


class TestMockRoutes:
    def test_generate_mock_routes_returns_three_options(self):
        routes = analyzer.generate_mock_routes("Koramangala", "Whitefield")
        assert len(routes) == 3

    def test_mock_routes_are_sorted_by_ascending_ratio(self):
        routes = analyzer.generate_mock_routes("Koramangala", "Whitefield")
        ratios = [r.traffic_ratio for r in routes]
        # generate_mock_routes doesn't guarantee sort order itself, but
        # sort_routes_by_traffic should always produce ascending order
        sorted_routes = analyzer.sort_routes_by_traffic(routes)
        sorted_ratios = [r.traffic_ratio for r in sorted_routes]
        assert sorted_ratios == sorted(sorted_ratios)
