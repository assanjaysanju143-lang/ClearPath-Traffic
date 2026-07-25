"""
Tests for services/live_feed.py — the camera report store that closes the
loop between the ML detector and the routing engine.
"""

import time
import pytest
from services.live_feed import LiveFeed


def test_report_then_all_reports_returns_it():
    feed = LiveFeed()
    feed.report("Outer Ring Road", total_vehicles=40, weighted_density=25.0,
                density_level="HIGH", traffic_ratio=0.8)
    reports = feed.all_reports()
    assert len(reports) == 1
    assert reports[0]["location_name"] == "Outer Ring Road"
    assert reports[0]["traffic_ratio"] == 0.8


def test_match_is_case_insensitive_substring():
    feed = LiveFeed()
    feed.report("Outer Ring Road", total_vehicles=10, weighted_density=5.0,
                density_level="LOW", traffic_ratio=0.1)
    match = feed.match("Turn right onto outer ring road near the mall")
    assert match is not None
    assert match["location_name"] == "Outer Ring Road"


def test_match_returns_none_when_no_location_mentioned():
    feed = LiveFeed()
    feed.report("Outer Ring Road", total_vehicles=10, weighted_density=5.0,
                density_level="LOW", traffic_ratio=0.1)
    assert feed.match("Head north on 100 Feet Road") is None


def test_match_returns_none_for_empty_text():
    feed = LiveFeed()
    feed.report("Outer Ring Road", 10, 5.0, "LOW", 0.1)
    assert feed.match("") is None
    assert feed.match(None) is None


def test_expired_report_is_pruned_from_all_reports():
    feed = LiveFeed()
    feed.report("Silk Board", 10, 5.0, "LOW", 0.1)
    # Manually backdate the report past the TTL
    feed._reports["silk board"]["reported_at"] = time.time() - 200  # TTL is 120s
    assert feed.all_reports() == []


def test_expired_report_no_longer_matches():
    feed = LiveFeed()
    feed.report("Silk Board", 10, 5.0, "LOW", 0.1)
    feed._reports["silk board"]["reported_at"] = time.time() - 200
    assert feed.match("stuck near Silk Board junction") is None


def test_history_accumulates_across_multiple_reports():
    feed = LiveFeed()
    feed.report("Whitefield", 10, 5.0, "LOW", 0.1)
    feed.report("Whitefield", 15, 7.0, "MODERATE", 0.2)
    feed.report("Whitefield", 20, 9.0, "HIGH", 0.4)
    history = feed.get_history("Whitefield")
    assert len(history) == 3
    assert [h["traffic_ratio"] for h in history] == [0.1, 0.2, 0.4]


def test_history_is_case_insensitive_key():
    feed = LiveFeed()
    feed.report("Whitefield", 10, 5.0, "LOW", 0.1)
    assert len(feed.get_history("WHITEFIELD")) == 1
    assert len(feed.get_history("whitefield")) == 1


def test_history_older_than_window_is_pruned():
    feed = LiveFeed()
    feed.report("Jayanagar", 10, 5.0, "LOW", 0.1)
    # Backdate past the 30-minute history window
    feed._history["jayanagar"][0]["timestamp"] = time.time() - 3600
    assert feed.get_history("Jayanagar") == []


def test_known_locations_reflects_active_history():
    feed = LiveFeed()
    feed.report("Hebbal", 10, 5.0, "LOW", 0.1)
    feed.report("Yeshwanthpur", 10, 5.0, "LOW", 0.1)
    locations = feed.known_locations()
    assert set(locations) == {"Hebbal", "Yeshwanthpur"}


def test_report_updates_latest_but_keeps_history():
    """A second report for the same location should replace the 'latest'
    single reading but not erase the accumulated history."""
    feed = LiveFeed()
    feed.report("MG Road", 10, 5.0, "LOW", 0.1)
    feed.report("MG Road", 30, 20.0, "HIGH", 0.7)
    latest = feed.all_reports()
    assert len(latest) == 1
    assert latest[0]["traffic_ratio"] == 0.7
    assert len(feed.get_history("MG Road")) == 2
