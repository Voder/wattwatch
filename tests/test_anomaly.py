"""Tests for WattWatch anomaly detection engine."""

import pytest

from custom_components.wattwatch.anomaly import AnomalyDetector, AnomalyResult


def _warmup(detector: AnomalyDetector, value: float, count: int) -> None:
    """Prime detector with `count` samples at `value`."""
    for _ in range(count):
        detector.add_sample(value)


def _trigger_spike(
    detector: AnomalyDetector, value: float, times: int
) -> AnomalyResult:
    """Feed `times` identical spike samples, return last result."""
    result = None
    for _ in range(times):
        result = detector.add_sample(value)
    assert result is not None
    return result


class TestAnomalyDetector:
    """Test AnomalyDetector class."""

    def test_insufficient_samples_no_anomaly(self):
        """No anomaly when below min_samples."""
        detector = AnomalyDetector(
            window_size=100,
            threshold=3.0,
            min_samples=10,
            consecutive_required=1,
        )
        for i in range(9):
            result = detector.add_sample(100.0 + i)
            assert not result.is_anomaly
            assert result.anomaly_type is None
            assert result.sample_count == i + 1

    def test_normal_value_no_anomaly(self):
        """Normal values within threshold produce no anomaly."""
        detector = AnomalyDetector(
            window_size=100,
            threshold=3.0,
            min_samples=10,
            consecutive_required=1,
        )
        _warmup(detector, 100.0, 20)
        result = detector.add_sample(100.5)
        assert not result.is_anomaly
        assert result.anomaly_type is None

    def test_spike_detected_after_streak(self):
        """Sustained high value triggers spike after streak."""
        detector = AnomalyDetector(
            window_size=100,
            threshold=3.0,
            min_samples=10,
            min_deviation=1.0,
            consecutive_required=3,
        )
        # Varied baseline so MAD > 0
        for i in range(60):
            detector.add_sample(100.0 + (i % 3))
        result = _trigger_spike(detector, 500.0, 3)
        assert result.is_anomaly
        assert result.anomaly_type == "spike"
        assert result.z_score > 3.0

    def test_transient_spike_suppressed(self):
        """Single-sample spike is filtered by streak requirement."""
        detector = AnomalyDetector(
            window_size=100,
            threshold=3.0,
            min_samples=10,
            min_deviation=1.0,
            consecutive_required=3,
        )
        for i in range(60):
            detector.add_sample(100.0 + (i % 3))
        # One spike sample — raw anomaly, not confirmed
        result = detector.add_sample(500.0)
        assert not result.is_anomaly
        assert abs(result.z_score) >= 3.0
        # Back to normal — streak resets
        result = detector.add_sample(101.0)
        assert not result.is_anomaly

    def test_drop_detected_after_streak(self):
        """Sustained low value triggers drop anomaly."""
        detector = AnomalyDetector(
            window_size=100,
            threshold=3.0,
            min_samples=10,
            min_deviation=1.0,
            consecutive_required=3,
        )
        for i in range(60):
            detector.add_sample(100.0 + (i % 3))
        result = _trigger_spike(detector, -200.0, 3)
        assert result.is_anomaly
        assert result.anomaly_type == "drop"
        assert result.z_score < -3.0

    def test_direction_change_resets_streak(self):
        """Switching spike→drop within streak does not confirm."""
        detector = AnomalyDetector(
            window_size=100,
            threshold=3.0,
            min_samples=10,
            min_deviation=1.0,
            consecutive_required=3,
        )
        for i in range(60):
            detector.add_sample(100.0 + (i % 3))
        # 2 spikes, then drop — should reset
        detector.add_sample(500.0)
        detector.add_sample(500.0)
        result = detector.add_sample(-200.0)
        assert not result.is_anomaly  # streak restarted at 1

    def test_flat_window_with_floor_no_false_anomaly(self):
        """Min deviation floor prevents false anomalies on flat windows."""
        detector = AnomalyDetector(
            window_size=100,
            threshold=3.0,
            min_samples=5,
            min_deviation=5.0,
            consecutive_required=1,
        )
        _warmup(detector, 50.0, 10)
        # 52.0 is within min_deviation floor — score = 2/5 = 0.4
        result = detector.add_sample(52.0)
        assert not result.is_anomaly
        assert result.stdev >= 5.0

    def test_bimodal_window_no_false_spike_on_mode_switch(self):
        """Bimodal fridge-like load: mode switch does not trigger anomaly."""
        detector = AnomalyDetector(
            window_size=100,
            threshold=3.0,
            min_samples=10,
            min_deviation=5.0,
            consecutive_required=3,
        )
        # Alternate idle/compressor: 30W and 100W
        for _ in range(25):
            detector.add_sample(30.0)
            detector.add_sample(100.0)
        # Another mode switch — within observed range, should not fire
        result = detector.add_sample(100.0)
        assert not result.is_anomaly

    def test_anomaly_value_added_to_window(self):
        """Anomalous values are included in the window."""
        detector = AnomalyDetector(
            window_size=30,
            threshold=3.0,
            min_samples=10,
            min_deviation=1.0,
            consecutive_required=1,
        )
        for i in range(15):
            detector.add_sample(100.0 + (i % 3))
        detector.add_sample(101.0)
        detector.add_sample(500.0)  # raw anomaly
        assert 500.0 in detector._window

    def test_window_maxlen_respected(self):
        """Window does not exceed maxlen."""
        detector = AnomalyDetector(window_size=10, threshold=3.0, min_samples=5)
        for i in range(20):
            detector.add_sample(float(i))
        assert detector.sample_count == 10

    def test_result_fields(self):
        """AnomalyResult contains expected fields."""
        detector = AnomalyDetector(
            window_size=100, threshold=3.0, min_samples=5
        )
        for i in range(10):
            detector.add_sample(100.0 + i * 0.1)
        result = detector.add_sample(100.5)
        assert isinstance(result, AnomalyResult)
        assert isinstance(result.z_score, float)
        assert isinstance(result.mean, float)
        assert isinstance(result.stdev, float)
        assert result.current_value == 100.5
        assert result.sample_count == 11

    def test_serialization_roundtrip(self):
        """to_dict/from_dict preserves detector state."""
        detector = AnomalyDetector(
            window_size=50,
            threshold=2.5,
            min_samples=8,
            min_deviation=7.5,
            consecutive_required=4,
        )
        for i in range(30):
            detector.add_sample(100.0 + i)

        data = detector.to_dict()
        restored = AnomalyDetector.from_dict(data)

        assert list(restored._window) == list(detector._window)
        assert restored._window.maxlen == 50
        assert restored._threshold == 2.5
        assert restored._min_samples == 8
        assert restored._min_deviation == 7.5
        assert restored._consecutive_required == 4

    def test_from_dict_backward_compat(self):
        """Old persisted data without new keys uses defaults."""
        data = {
            "window": [1.0, 2.0, 3.0],
            "window_size": 100,
            "threshold": 3.0,
            "min_samples": 10,
        }
        detector = AnomalyDetector.from_dict(data)
        assert detector._min_deviation == 5.0
        assert detector._consecutive_required == 3

    def test_update_settings_threshold(self):
        """Updating threshold changes detection sensitivity."""
        detector = AnomalyDetector(
            window_size=100,
            threshold=5.0,
            min_samples=5,
            min_deviation=1.0,
            consecutive_required=1,
        )
        for i in range(40):
            detector.add_sample(80.0 + (i % 5) * 10.0)

        result = detector.add_sample(145.0)
        assert not result.is_anomaly

        detector.update_settings(threshold=2.0)
        result = detector.add_sample(145.0)
        assert result.is_anomaly

    def test_update_settings_window_size(self):
        """Updating window_size creates new deque preserving data."""
        detector = AnomalyDetector(window_size=100, threshold=3.0, min_samples=5)
        for i in range(20):
            detector.add_sample(float(i))
        assert detector.sample_count == 20

        detector.update_settings(window_size=10)
        assert detector.sample_count == 10
        assert detector._window.maxlen == 10

    def test_update_settings_consecutive_resets_streak(self):
        """Changing consecutive_required clears streak state."""
        detector = AnomalyDetector(
            window_size=100,
            threshold=3.0,
            min_samples=10,
            min_deviation=1.0,
            consecutive_required=5,
        )
        for i in range(60):
            detector.add_sample(100.0 + (i % 3))
        detector.add_sample(500.0)
        detector.add_sample(500.0)
        assert detector._streak_count == 2

        detector.update_settings(consecutive_required=2)
        assert detector._streak_count == 0
        assert detector._streak_type is None

    def test_negative_values_allowed(self):
        """Negative values (e.g. solar export) are valid."""
        detector = AnomalyDetector(
            window_size=100,
            threshold=3.0,
            min_samples=5,
            min_deviation=1.0,
            consecutive_required=1,
        )
        _warmup(detector, -50.0, 10)
        detector.add_sample(-49.0)
        result = detector.add_sample(-50.5)
        assert not result.is_anomaly


class TestAnomalyDetectorEdgeCases:
    """Edge case tests."""

    def test_single_sample(self):
        """Single sample returns no anomaly."""
        detector = AnomalyDetector(min_samples=10)
        result = detector.add_sample(42.0)
        assert not result.is_anomaly
        assert result.sample_count == 1

    def test_exact_min_samples(self):
        """Detection activates exactly at min_samples."""
        detector = AnomalyDetector(
            window_size=100, threshold=3.0, min_samples=5, min_deviation=1.0
        )
        for _ in range(4):
            detector.add_sample(100.0)
        detector.add_sample(101.0)
        result = detector.add_sample(100.0)
        assert result.mean > 0

    def test_from_dict_empty_window(self):
        """Restore from empty window."""
        data = {
            "window": [],
            "window_size": 100,
            "threshold": 3.0,
            "min_samples": 10,
        }
        detector = AnomalyDetector.from_dict(data)
        assert detector.sample_count == 0
        result = detector.add_sample(42.0)
        assert not result.is_anomaly

    def test_zero_mad_uses_floor(self):
        """All-identical window: MAD=0, floor prevents div-by-zero."""
        detector = AnomalyDetector(
            window_size=100,
            threshold=3.0,
            min_samples=5,
            min_deviation=5.0,
            consecutive_required=1,
        )
        _warmup(detector, 50.0, 10)
        # Value within floor — no anomaly
        result = detector.add_sample(52.0)
        assert not result.is_anomaly
        # Value far beyond floor — anomaly
        result = detector.add_sample(200.0)
        assert result.is_anomaly
