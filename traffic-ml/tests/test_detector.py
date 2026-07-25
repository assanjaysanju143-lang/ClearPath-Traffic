"""
Tests for detector.py — the YOLO26 vehicle detection wrapper.

Requires the real ultralytics package and model weights (auto-downloaded on
first run), so this is heavier and slower than the backend's test suite —
run it separately:
    cd traffic-ml && pytest

The model is loaded once per test session (it's slow to load) via a
session-scoped fixture, then reused across tests.
"""

import os
import pytest
import cv2
import numpy as np

from detector import VehicleDetector, DENSITY_THRESHOLDS

# Ultralytics ships a couple of sample images with the package itself —
# using one of these means this test suite needs no test-image assets of
# its own and works in any environment with ultralytics installed.
import ultralytics
SAMPLE_IMAGE = os.path.join(os.path.dirname(ultralytics.__file__), "assets", "bus.jpg")


@pytest.fixture(scope="session")
def detector():
    return VehicleDetector(model_size="n", confidence=0.35, model_family="yolo26")


@pytest.fixture(scope="session")
def sample_frame():
    frame = cv2.imread(SAMPLE_IMAGE)
    assert frame is not None, f"Could not load sample image at {SAMPLE_IMAGE}"
    return frame


class TestModelLoading:
    def test_loads_default_family_and_size(self, detector):
        assert detector.model_family == "yolo26"
        assert detector.model_size == "n"

    def test_rejects_unknown_model_family(self):
        with pytest.raises(ValueError):
            VehicleDetector(model_family="yolo99")


class TestDetection:
    def test_detects_at_least_one_vehicle_in_sample_image(self, detector, sample_frame):
        # bus.jpg is a known image containing a bus — a real, non-trivial
        # sanity check that the model is actually detecting, not just
        # returning an empty/default result.
        result = detector.detect_frame(sample_frame)
        assert result.total_vehicles >= 1
        assert "bus" in result.vehicle_counts

    def test_traffic_ratio_is_normalized(self, detector, sample_frame):
        result = detector.detect_frame(sample_frame)
        assert 0.0 <= result.traffic_ratio <= 1.0

    def test_density_level_is_valid(self, detector, sample_frame):
        result = detector.detect_frame(sample_frame)
        assert result.density_level in ("LOW", "MODERATE", "HIGH")

    def test_annotated_frame_matches_input_dimensions(self, detector, sample_frame):
        result = detector.detect_frame(sample_frame)
        assert result.annotated_frame is not None
        assert result.annotated_frame.shape == sample_frame.shape

    def test_frame_id_increments_across_calls(self, detector, sample_frame):
        start_id = detector.frame_id
        detector.detect_frame(sample_frame)
        detector.detect_frame(sample_frame)
        assert detector.frame_id == start_id + 2

    def test_empty_frame_does_not_crash(self, detector):
        # A blank frame should detect nothing, not raise
        blank = np.zeros((480, 640, 3), dtype=np.uint8)
        result = detector.detect_frame(blank)
        assert result.total_vehicles == 0
        assert result.density_level == "LOW"


class TestDensityClassification:
    """_classify_density only depends on DENSITY_THRESHOLDS, not the model
    itself, so these are fast, pure-logic checks."""

    def test_zero_weighted_density_is_low(self, detector):
        assert detector._classify_density(0.0) == "LOW"

    def test_thresholds_are_monotonically_ordered(self):
        # LOW < MODERATE < HIGH ranges shouldn't overlap or go backwards —
        # a broken threshold table would silently misclassify everything.
        bounds = [lo for lo, hi in DENSITY_THRESHOLDS.values()]
        assert bounds == sorted(bounds)

    def test_value_above_all_thresholds_falls_back_to_high(self, detector):
        assert detector._classify_density(10_000.0) == "HIGH"
