"""Tests for WattWatch anomaly detection engine."""

import time

import pytest

from custom_components.wattwatch.anomaly import (
    AnomalyDetector,
    AnomalyResult,
    _WARMUP_SIZE,
    _MIN_CYCLES_PER_STATE,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _warmup(detector: AnomalyDetector, value: float, count: int, t_start: float = 0.0, dt: float = 1.0) -> float:
    """Feed `count` samples at `value`, return next timestamp."""
    t = t_start
    for _ in range(count):
        detector.add_sample(value, t)
        t += dt
    return t


def _feed(detector: AnomalyDetector, value: float, count: int, t_start: float, dt: float = 1.0) -> float:
    """Feed `count` samples, return next timestamp."""
    t = t_start
    for _ in range(count):
        result = detector.add_sample(value, t)
        t += dt
    return t


# ---------------------------------------------------------------------------
# Warmup phase
# ---------------------------------------------------------------------------

class TestWarmup:
    def test_no_anomaly_during_warmup(self):
        d = AnomalyDetector(window_size=100, threshold=3.0, min_samples=5)
        for i in range(_WARMUP_SIZE - 1):
            r = d.add_sample(100.0 + i, float(i))
            assert not r.is_anomaly
            assert r.sample_count == i + 1

    def test_warmup_completes_at_threshold(self):
        d = AnomalyDetector(window_size=100, threshold=3.0, min_samples=5)
        for i in range(_WARMUP_SIZE):
            d.add_sample(100.0, float(i))
        # After warmup: sample_count == _WARMUP_SIZE
        assert d._warmup_complete


# ---------------------------------------------------------------------------
# Non-cyclic fallback (unimodal window)
# ---------------------------------------------------------------------------

class TestNonCyclicFallback:
    """Detector in non-cyclic IQR mode."""

    def _make_unimodal(self, base: float = 100.0, spread: float = 5.0) -> tuple[AnomalyDetector, float]:
        """Return detector primed with unimodal data and next timestamp."""
        d = AnomalyDetector(
            window_size=100,
            threshold=3.0,
            min_samples=10,
            min_deviation=1.0,
            consecutive_required=3,
        )
        # Vary slightly so IQR > 0
        t = 0.0
        for i in range(60):
            d.add_sample(base + (i % 5) * spread / 5, t)
            t += 1.0
        assert not d._is_cyclic, "Should be unimodal"
        return d, t

    def test_normal_value_no_anomaly(self):
        d, t = self._make_unimodal()
        r = d.add_sample(101.0, t)
        assert not r.is_anomaly

    def test_spike_detected_after_streak(self):
        d, t = self._make_unimodal(base=100.0, spread=3.0)
        for i in range(3):
            r = d.add_sample(500.0, t + i)
        assert r.is_anomaly
        assert r.anomaly_type == "spike"
        assert r.z_score > 3.0

    def test_transient_spike_suppressed(self):
        d, t = self._make_unimodal()
        r = d.add_sample(500.0, t)
        assert not r.is_anomaly  # streak=1, needs 3
        r = d.add_sample(100.0, t + 1)
        assert not r.is_anomaly  # streak reset

    def test_drop_detected_after_streak(self):
        d, t = self._make_unimodal(base=100.0, spread=3.0)
        for i in range(3):
            r = d.add_sample(-200.0, t + i)
        assert r.is_anomaly
        assert r.anomaly_type == "drop"
        assert r.z_score < -3.0

    def test_direction_change_resets_streak(self):
        d, t = self._make_unimodal(base=100.0, spread=3.0)
        d.add_sample(500.0, t)
        d.add_sample(500.0, t + 1)
        r = d.add_sample(-200.0, t + 2)
        assert not r.is_anomaly  # streak restarted at 1

    def test_flat_window_floor_prevents_false_anomaly(self):
        d = AnomalyDetector(
            window_size=100, threshold=3.0, min_samples=5,
            min_deviation=5.0, consecutive_required=1,
        )
        _warmup(d, 50.0, 60)
        r = d.add_sample(52.0, 60.0)
        assert not r.is_anomaly
        assert r.stdev >= 5.0

    def test_negative_values_allowed(self):
        d = AnomalyDetector(
            window_size=100, threshold=3.0, min_samples=5,
            min_deviation=1.0, consecutive_required=1,
        )
        _warmup(d, -50.0, 60)
        r = d.add_sample(-50.5, 60.0)
        assert not r.is_anomaly


# ---------------------------------------------------------------------------
# Cyclic mode — bimodal detection
# ---------------------------------------------------------------------------

class TestBimodalDetection:
    def _make_bimodal(self, low: float = 0.0, high: float = 60.0, ratio: float = 0.2) -> AnomalyDetector:
        """Return detector that has seen bimodal data and entered cyclic mode."""
        d = AnomalyDetector(
            window_size=100, threshold=3.0, min_samples=5,
            min_deviation=5.0, consecutive_required=3,
        )
        n = _WARMUP_SIZE + 10
        t = 0.0
        for i in range(n):
            v = low if (i % 10 < int(10 * ratio)) else high
            d.add_sample(v, t)
            t += 1.0
        return d

    def test_bimodal_window_enters_cyclic_mode(self):
        d = self._make_bimodal(low=0.0, high=60.0)
        assert d._is_cyclic
        assert d._mode_threshold is not None
        assert 0.0 < d._mode_threshold < 60.0

    def test_unimodal_stays_non_cyclic(self):
        d = AnomalyDetector(window_size=100, threshold=3.0, min_samples=5)
        t = 0.0
        for i in range(60):
            d.add_sample(100.0 + (i % 5), t)
            t += 1.0
        assert not d._is_cyclic

    def test_bimodal_threshold_midpoint(self):
        d = self._make_bimodal(low=0.0, high=60.0)
        # Threshold should be between the two modes
        assert 5.0 < d._mode_threshold < 55.0

    def test_mode_switch_does_not_trigger_anomaly(self):
        """A normal on→off transition in cyclic mode must not fire."""
        d = self._make_bimodal(low=0.0, high=60.0)
        # Feed a low-state sample (compressor off)
        r = d.add_sample(0.0, 100.0)
        assert not r.is_anomaly

    def test_sparse_off_samples_still_detected(self):
        """Bimodal detected even when off-samples are sparse (3 out of 50)."""
        d = AnomalyDetector(window_size=100, threshold=3.0, min_samples=5, min_deviation=5.0)
        t = 0.0
        # 3 off-samples scattered among many on-samples
        off_positions = {5, 20, 35}
        for i in range(_WARMUP_SIZE + 20):
            v = 0.0 if i in off_positions else 60.0 + (i % 5) * 0.5
            d.add_sample(v, t)
            t += 1.0
        assert d._is_cyclic


# ---------------------------------------------------------------------------
# Cyclic mode — cycle-feature scoring
# ---------------------------------------------------------------------------

class TestCyclicFeatureScoring:
    """Build up a detector with known cycle history then inject anomalies."""

    def _build_cyclic_detector(
        self,
        n_cycles: int = 10,
        on_duration: float = 300.0,  # 5 min
        off_duration: float = 600.0,  # 10 min
        on_power: float = 60.0,
        dt: float = 30.0,  # sample interval
    ) -> tuple[AnomalyDetector, float]:
        """Prime detector with n_cycles of regular ON/OFF behaviour."""
        d = AnomalyDetector(
            window_size=100, threshold=3.0, min_samples=3,
            min_deviation=5.0, consecutive_required=3,
        )
        t = 0.0
        # Warmup with ON samples first so it gets past _WARMUP_SIZE
        for _ in range(_WARMUP_SIZE):
            d.add_sample(on_power, t)
            t += dt

        # Feed complete cycles
        for _ in range(n_cycles):
            # ON phase
            end_on = t + on_duration
            while t < end_on:
                d.add_sample(on_power + (t % 2), t)
                t += dt
            # Transition to OFF
            d.add_sample(0.0, t)
            t += dt
            # OFF phase (silent — only one sample while off)
            t += off_duration
            # Transition back to ON
            d.add_sample(on_power, t)
            t += dt

        return d, t

    def test_normal_cycle_no_anomaly(self):
        d, t = self._build_cyclic_detector(n_cycles=8)
        # Normal on-duration sample
        r = d.add_sample(60.0, t)
        assert not r.is_anomaly

    def test_stuck_on_fires_after_excess_duration(self):
        """Stuck on: current on-duration >> expected."""
        d, t = self._build_cyclic_detector(n_cycles=8, on_duration=300.0)
        # Start a new ON phase and let it run 3× the expected duration
        d.add_sample(0.0, t)       # enter OFF briefly to record previous half-cycle
        t += 1.0
        d.add_sample(60.0, t)      # back to ON
        # Jump to 3× expected duration without state change
        t_stuck = t + 300.0 * 3 + 200.0
        r = d.add_sample(60.0, t_stuck)
        assert r.is_anomaly
        assert r.anomaly_type == "stuck_on"
        assert r.z_score > 3.0

    def test_stuck_off_fires_after_excess_duration(self):
        """Stuck off: off-duration >> expected."""
        d, t = self._build_cyclic_detector(n_cycles=8, off_duration=600.0)
        # Trigger OFF transition
        d.add_sample(0.0, t)
        # Jump to 3× expected off-duration
        t_stuck = t + 600.0 * 3 + 200.0
        r = d.add_sample(0.0, t_stuck)
        assert r.is_anomaly
        assert r.anomaly_type == "stuck_off"
        assert r.z_score > 3.0

    def test_normal_off_duration_no_anomaly(self):
        d, t = self._build_cyclic_detector(n_cycles=8, off_duration=600.0)
        d.add_sample(0.0, t)
        # Within expected off time
        r = d.add_sample(0.0, t + 300.0)
        assert not r.is_anomaly

    def test_power_spike_in_on_state(self):
        """Sustained power spike in ON state fires power_spike."""
        d, t = self._build_cyclic_detector(n_cycles=8, on_power=60.0)
        # Start a new ON phase at elevated power
        d.add_sample(0.0, t)
        t += 1.0
        r = None
        for i in range(5):
            r = d.add_sample(120.0, t + i)  # 2× normal
        assert r.is_anomaly
        assert r.anomaly_type == "power_spike"

    def test_power_drop_in_on_state(self):
        """Sustained power drop in ON state fires power_drop."""
        d, t = self._build_cyclic_detector(n_cycles=8, on_power=60.0)
        # Threshold ≈ 30 W (midpoint of 0 and 60). Use 35 W: above threshold
        # (stays in "on" state) but far below normal 60 W → power_drop.
        d.add_sample(0.0, t)
        t += 1.0
        r = None
        for i in range(5):
            r = d.add_sample(35.0, t + i)
        assert r.is_anomaly
        assert r.anomaly_type == "power_drop"

    def test_short_cycle_no_anomaly(self):
        """Early recovery (shorter on-duration than expected) is not an anomaly."""
        d, t = self._build_cyclic_detector(n_cycles=8, on_duration=300.0)
        d.add_sample(0.0, t)
        t += 1.0
        d.add_sample(60.0, t)
        # Feed sample at only half the expected duration
        r = d.add_sample(60.0, t + 100.0)
        assert not r.is_anomaly


# ---------------------------------------------------------------------------
# Common edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_single_sample(self):
        d = AnomalyDetector(min_samples=10)
        r = d.add_sample(42.0, 0.0)
        assert not r.is_anomaly
        assert r.sample_count == 1

    def test_window_maxlen_respected(self):
        d = AnomalyDetector(window_size=10, threshold=3.0, min_samples=5)
        for i in range(20):
            d.add_sample(float(i), float(i))
        assert d.sample_count == 10

    def test_result_fields_present(self):
        d = AnomalyDetector(window_size=100, threshold=3.0, min_samples=5)
        for i in range(10):
            d.add_sample(100.0 + i * 0.1, float(i))
        r = d.add_sample(100.5, 10.0)
        assert isinstance(r, AnomalyResult)
        assert isinstance(r.z_score, float)
        assert isinstance(r.mean, float)
        assert isinstance(r.stdev, float)
        assert r.current_value == 100.5

    def test_anomalous_value_added_to_window(self):
        d = AnomalyDetector(
            window_size=30, threshold=3.0, min_samples=10,
            min_deviation=1.0, consecutive_required=1,
        )
        for i in range(15):
            d.add_sample(100.0 + (i % 3), float(i))
        d.add_sample(500.0, 15.0)
        assert 500.0 in d._window


# ---------------------------------------------------------------------------
# Serialisation / persistence
# ---------------------------------------------------------------------------

class TestSerialisation:
    def test_roundtrip_non_cyclic(self):
        d = AnomalyDetector(
            window_size=50, threshold=2.5, min_samples=8,
            min_deviation=7.5, consecutive_required=4,
        )
        for i in range(30):
            d.add_sample(100.0 + i, float(i))

        data = d.to_dict()
        r = AnomalyDetector.from_dict(data)

        assert list(r._window) == list(d._window)
        assert r._window.maxlen == 50
        assert r._threshold == 2.5
        assert r._min_samples == 8
        assert r._min_deviation == 7.5
        assert r._consecutive_required == 4

    def test_roundtrip_cyclic(self):
        d = AnomalyDetector(window_size=100, threshold=3.0, min_samples=5)
        t = 0.0
        for i in range(_WARMUP_SIZE + 20):
            v = 0.0 if (i % 10 < 2) else 60.0
            d.add_sample(v, t)
            t += 1.0

        data = d.to_dict()
        r = AnomalyDetector.from_dict(data)

        assert r._is_cyclic == d._is_cyclic
        assert r._mode_threshold == d._mode_threshold
        assert r._warmup_complete
        assert len(r._half_cycles) == len(d._half_cycles)
        assert list(r._window) == list(d._window)

    def test_backward_compat_missing_keys(self):
        """Old persisted data without new keys uses defaults."""
        data = {
            "window": [1.0, 2.0, 3.0],
            "window_size": 100,
            "threshold": 3.0,
            "min_samples": 10,
        }
        r = AnomalyDetector.from_dict(data)
        assert r._min_deviation == 5.0
        assert r._consecutive_required == 3
        assert not r._is_cyclic
        assert not r._warmup_complete

    def test_from_dict_empty_window(self):
        data = {
            "window": [],
            "window_size": 100,
            "threshold": 3.0,
            "min_samples": 10,
        }
        d = AnomalyDetector.from_dict(data)
        assert d.sample_count == 0
        r = d.add_sample(42.0, 0.0)
        assert not r.is_anomaly


# ---------------------------------------------------------------------------
# update_settings
# ---------------------------------------------------------------------------

class TestUpdateSettings:
    def test_threshold_change(self):
        # Use a flat baseline so scale = min_deviation = 1.0,
        # making the z-score easy to reason about.
        d = AnomalyDetector(
            window_size=100, threshold=5.0, min_samples=5,
            min_deviation=1.0, consecutive_required=1,
        )
        for i in range(60):
            d.add_sample(100.0, float(i))

        # z = (110 - 100) / 1.0 = 10 — above both thresholds
        # but first check at threshold=5.0 it fires, then lower is irrelevant;
        # instead check a value that is in [2, 5) range:
        # z = (103 - 100) / 1.0 = 3 → no at 5.0, yes at 2.0
        r = d.add_sample(103.0, 60.0)
        assert not r.is_anomaly

        d.update_settings(threshold=2.0)
        r = d.add_sample(103.0, 61.0)
        assert r.is_anomaly

    def test_window_size_change_preserves_data(self):
        d = AnomalyDetector(window_size=100, threshold=3.0, min_samples=5)
        for i in range(20):
            d.add_sample(float(i), float(i))
        d.update_settings(window_size=10)
        assert d.sample_count == 10
        assert d._window.maxlen == 10

    def test_consecutive_required_resets_streak(self):
        d = AnomalyDetector(
            window_size=100, threshold=3.0, min_samples=10,
            min_deviation=1.0, consecutive_required=5,
        )
        for i in range(60):
            d.add_sample(100.0 + (i % 3), float(i))
        d.add_sample(500.0, 60.0)
        d.add_sample(500.0, 61.0)
        assert d._streak_count == 2

        d.update_settings(consecutive_required=2)
        assert d._streak_count == 0
        assert d._streak_type is None
