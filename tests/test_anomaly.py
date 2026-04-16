"""Tests for WattWatch anomaly detection engine."""

import pytest

from custom_components.wattwatch.anomaly import AnomalyDetector, AnomalyResult


class TestAnomalyDetector:
    """Test AnomalyDetector class."""

    def test_insufficient_samples_no_anomaly(self):
        """No anomaly when below min_samples."""
        detector = AnomalyDetector(window_size=100, threshold=3.0, min_samples=10)
        for i in range(9):
            result = detector.add_sample(100.0 + i)
            assert not result.is_anomaly
            assert result.anomaly_type is None
            assert result.sample_count == i + 1

    def test_normal_value_no_anomaly(self):
        """Normal values within threshold produce no anomaly."""
        detector = AnomalyDetector(window_size=100, threshold=3.0, min_samples=10)
        for _ in range(20):
            detector.add_sample(100.0)
        result = detector.add_sample(100.5)
        assert not result.is_anomaly
        assert result.anomaly_type is None

    def test_spike_detected(self):
        """High value triggers spike anomaly."""
        detector = AnomalyDetector(window_size=100, threshold=3.0, min_samples=10)
        for _ in range(50):
            detector.add_sample(100.0)
        # Add slight variation so stdev > 0
        for _ in range(10):
            detector.add_sample(101.0)
        result = detector.add_sample(500.0)
        assert result.is_anomaly
        assert result.anomaly_type == "spike"
        assert result.z_score > 3.0

    def test_drop_detected(self):
        """Low value triggers drop anomaly."""
        detector = AnomalyDetector(window_size=100, threshold=3.0, min_samples=10)
        for _ in range(50):
            detector.add_sample(100.0)
        for _ in range(10):
            detector.add_sample(101.0)
        result = detector.add_sample(-200.0)
        assert result.is_anomaly
        assert result.anomaly_type == "drop"
        assert result.z_score < -3.0

    def test_zero_stdev_no_anomaly(self):
        """Identical values (stdev=0) never produce anomaly."""
        detector = AnomalyDetector(window_size=100, threshold=3.0, min_samples=5)
        for _ in range(10):
            result = detector.add_sample(50.0)
        assert not result.is_anomaly
        assert result.stdev == 0.0

    def test_anomaly_value_added_to_window(self):
        """Anomalous values are included in the window."""
        detector = AnomalyDetector(window_size=20, threshold=3.0, min_samples=10)
        for _ in range(15):
            detector.add_sample(100.0)
        detector.add_sample(101.0)
        detector.add_sample(500.0)  # anomaly
        assert detector.sample_count == 17
        # The 500.0 should be in the window
        assert 500.0 in detector._window

    def test_window_maxlen_respected(self):
        """Window does not exceed maxlen."""
        detector = AnomalyDetector(window_size=10, threshold=3.0, min_samples=5)
        for i in range(20):
            detector.add_sample(float(i))
        assert detector.sample_count == 10

    def test_result_fields(self):
        """AnomalyResult contains expected fields."""
        detector = AnomalyDetector(window_size=100, threshold=3.0, min_samples=5)
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
        detector = AnomalyDetector(window_size=50, threshold=2.5, min_samples=8)
        for i in range(30):
            detector.add_sample(100.0 + i)

        data = detector.to_dict()
        restored = AnomalyDetector.from_dict(data)

        assert list(restored._window) == list(detector._window)
        assert restored._window.maxlen == 50
        assert restored._threshold == 2.5
        assert restored._min_samples == 8

    def test_update_settings_threshold(self):
        """Updating threshold changes detection sensitivity."""
        detector = AnomalyDetector(window_size=100, threshold=5.0, min_samples=5)
        # Create varied baseline: values 80-120
        for i in range(40):
            detector.add_sample(80.0 + (i % 5) * 10.0)

        # With threshold=5.0, value at ~3 stdev is not anomaly
        result = detector.add_sample(145.0)
        assert not result.is_anomaly

        # Lower threshold to 2.0
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
        # Should keep last 10 values
        assert detector.sample_count == 10
        assert detector._window.maxlen == 10

    def test_negative_values_allowed(self):
        """Negative values (e.g. solar export) are valid."""
        detector = AnomalyDetector(window_size=100, threshold=3.0, min_samples=5)
        for _ in range(10):
            detector.add_sample(-50.0)
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
        detector = AnomalyDetector(window_size=100, threshold=3.0, min_samples=5)
        for _ in range(4):
            detector.add_sample(100.0)
        # 5th sample — now at min_samples, detection should activate
        detector.add_sample(101.0)
        result = detector.add_sample(100.0)
        assert result.mean > 0  # mean computed from window

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
