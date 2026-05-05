"""Anomaly detection engine for WattWatch."""

from __future__ import annotations

import statistics
import time
from collections import deque
from dataclasses import dataclass
from typing import NamedTuple

# IQR → comparable to std for Gaussian data
_IQR_SCALE = 1.4826

# Warmup: raw samples to collect before first mode detection
_WARMUP_SIZE = 40
# Re-check mode periodically (every N samples)
_REDETECT_INTERVAL = 50
# Gap must exceed this multiple of the larger cluster's IQR to classify as bimodal
_BIMODAL_GAP_FACTOR = 4.0
# Minimum samples required in the smaller cluster for bimodal classification
_BIMODAL_MIN_CLUSTER_SIZE = 3
# Minimum half-cycles per state before duration scoring activates
_MIN_CYCLES_PER_STATE = 3
# Floor for duration stdev (seconds) — prevents hypersensitivity on regular cycles
_MIN_DURATION_STDEV = 60.0


@dataclass
class AnomalyResult:
    """Result of anomaly detection for a single sample."""

    is_anomaly: bool
    anomaly_type: str | None
    z_score: float
    current_value: float
    mean: float
    stdev: float
    sample_count: int


class _HalfCycle(NamedTuple):
    """A completed run of a single state (on or off)."""

    state: str        # "on" | "off"
    duration: float   # seconds
    mean_power: float # mean watts during this run


class AnomalyDetector:
    """Cycle-aware anomaly detector.

    Automatically classifies the monitored device as cyclic (bimodal power
    distribution, e.g. compressors, fridges) or non-cyclic and applies the
    appropriate detection strategy.

    Cyclic mode — tracks half-cycle features:
      - stuck_on  : on-duration >> historical mean (door open, motor fault)
      - stuck_off : off-duration >> historical mean (dead compressor)
      - power_spike / power_drop : running-state consumption change

    Non-cyclic mode — IQR-based z-score with streak filter (robust fallback).
    """

    def __init__(
        self,
        window_size: int = 100,
        threshold: float = 3.0,
        min_samples: int = 10,
        min_deviation: float = 5.0,
        consecutive_required: int = 3,
    ) -> None:
        self._window_size = window_size
        self._threshold = threshold
        self._min_samples = min_samples
        self._min_deviation = min_deviation
        self._consecutive_required = max(1, consecutive_required)

        # Raw value window — always maintained for mode detection
        self._window: deque[float] = deque(maxlen=window_size)

        # Mode detection state
        self._mode_threshold: float | None = None
        self._is_cyclic: bool = False
        self._warmup_complete: bool = False
        self._samples_since_redetect: int = 0

        # State machine (cyclic mode)
        self._current_state: str | None = None  # "on" | "off"
        self._state_start: float = 0.0
        self._state_values: list[float] = []

        # Completed half-cycle history
        self._half_cycles: deque[_HalfCycle] = deque(maxlen=window_size)

        # Non-cyclic streak filter
        self._streak_type: str | None = None
        self._streak_count: int = 0

    @property
    def sample_count(self) -> int:
        """Return number of raw samples in window."""
        return len(self._window)

    def add_sample(self, value: float, timestamp: float | None = None) -> AnomalyResult:
        """Add a sample and return an AnomalyResult.

        Pass the event timestamp (epoch seconds) for accurate cycle duration
        measurement. Falls back to wall clock if omitted.
        """
        now = timestamp if timestamp is not None else time.time()
        self._window.append(value)

        # Phase 1: warmup — accumulate raw samples before first mode check
        if not self._warmup_complete:
            if len(self._window) >= _WARMUP_SIZE:
                self._detect_mode()
                self._warmup_complete = True
            return AnomalyResult(
                is_anomaly=False,
                anomaly_type=None,
                z_score=0.0,
                current_value=value,
                mean=0.0,
                stdev=0.0,
                sample_count=len(self._window),
            )

        # Periodic re-detection so mode can change as device behaviour shifts
        self._samples_since_redetect += 1
        if self._samples_since_redetect >= _REDETECT_INTERVAL:
            self._samples_since_redetect = 0
            self._detect_mode()

        if self._is_cyclic:
            return self._cyclic_check(value, now)
        return self._fallback_check(value)

    # ------------------------------------------------------------------
    # Mode detection
    # ------------------------------------------------------------------

    def _detect_mode(self) -> None:
        """Classify current window as cyclic (bimodal) or non-cyclic."""
        if len(self._window) < 10:
            return

        sorted_vals = sorted(self._window)
        n = len(sorted_vals)

        # Find the largest gap between adjacent sorted values
        gaps = [sorted_vals[i + 1] - sorted_vals[i] for i in range(n - 1)]
        max_gap = max(gaps)
        gap_idx = gaps.index(max_gap)

        low_cluster = sorted_vals[: gap_idx + 1]
        high_cluster = sorted_vals[gap_idx + 1 :]

        # Require a minimum number of samples in both clusters
        if (
            len(low_cluster) < _BIMODAL_MIN_CLUSTER_SIZE
            or len(high_cluster) < _BIMODAL_MIN_CLUSTER_SIZE
        ):
            self._set_non_cyclic()
            return

        # Gap must be large relative to within-cluster spread
        def _cluster_iqr(c: list[float]) -> float:
            m = len(c)
            if m < 4:
                return max(c[-1] - c[0], 0.0)
            return c[3 * m // 4] - c[m // 4]

        max_within_spread = max(
            _cluster_iqr(low_cluster),
            _cluster_iqr(high_cluster),
            self._min_deviation / 2,
        )

        was_cyclic = self._is_cyclic
        if max_gap > _BIMODAL_GAP_FACTOR * max_within_spread:
            threshold = (sorted_vals[gap_idx] + sorted_vals[gap_idx + 1]) / 2
            self._mode_threshold = threshold
            self._is_cyclic = True
            if not was_cyclic:
                # Reset state machine on first cyclic activation
                self._current_state = None
                self._state_values = []
        else:
            self._set_non_cyclic()

    def _set_non_cyclic(self) -> None:
        was_cyclic = self._is_cyclic
        self._is_cyclic = False
        self._mode_threshold = None
        if was_cyclic:
            self._streak_type = None
            self._streak_count = 0

    # ------------------------------------------------------------------
    # Cyclic mode
    # ------------------------------------------------------------------

    def _cyclic_check(self, value: float, now: float) -> AnomalyResult:
        """Detect anomalies using cycle-feature tracking."""
        new_state = "on" if value >= self._mode_threshold else "off"

        # Initialise state machine on first cyclic sample
        if self._current_state is None:
            self._current_state = new_state
            self._state_start = now
            self._state_values = [value]
            return AnomalyResult(
                is_anomaly=False,
                anomaly_type=None,
                z_score=0.0,
                current_value=value,
                mean=0.0,
                stdev=0.0,
                sample_count=len(self._window),
            )

        if new_state != self._current_state:
            # State transition: record completed half-cycle
            duration = max(now - self._state_start, 0.0)
            mean_power = statistics.mean(self._state_values) if self._state_values else 0.0
            self._half_cycles.append(
                _HalfCycle(
                    state=self._current_state,
                    duration=duration,
                    mean_power=mean_power,
                )
            )
            self._current_state = new_state
            self._state_start = now
            self._state_values = [value]
        else:
            self._state_values.append(value)

        # Need enough half-cycles of current state type to score against
        state_cycles = [hc for hc in self._half_cycles if hc.state == self._current_state]
        if len(state_cycles) < _MIN_CYCLES_PER_STATE:
            return AnomalyResult(
                is_anomaly=False,
                anomaly_type=None,
                z_score=0.0,
                current_value=value,
                mean=0.0,
                stdev=0.0,
                sample_count=len(self._window),
            )

        # --- Duration score ---
        current_duration = now - self._state_start
        durations = [hc.duration for hc in state_cycles]
        mean_dur = statistics.mean(durations)
        std_dur = max(
            statistics.stdev(durations) if len(durations) > 1 else 0.0,
            _MIN_DURATION_STDEV,
        )
        dur_score = (current_duration - mean_dur) / std_dur

        # --- Power score (ON state only) ---
        pow_score = 0.0
        mean_pow = 0.0
        std_pow = self._min_deviation
        if self._current_state == "on" and len(self._state_values) >= 3:
            on_powers = [hc.mean_power for hc in state_cycles]
            if len(on_powers) >= _MIN_CYCLES_PER_STATE:
                mean_pow = statistics.mean(on_powers)
                std_pow = max(
                    statistics.stdev(on_powers) if len(on_powers) > 1 else 0.0,
                    self._min_deviation,
                )
                current_pow = statistics.mean(self._state_values)
                pow_score = (current_pow - mean_pow) / std_pow

        # Anomaly decision:
        # - Duration exceeding threshold → stuck on / stuck off
        # - Power level deviating → power_spike / power_drop
        # - Shorter-than-expected duration is not actionable (early recovery)
        anomaly_type: str | None = None
        score = 0.0

        if dur_score >= self._threshold:
            anomaly_type = "stuck_on" if self._current_state == "on" else "stuck_off"
            score = dur_score
        elif abs(pow_score) >= self._threshold:
            anomaly_type = "power_spike" if pow_score > 0 else "power_drop"
            score = pow_score

        return AnomalyResult(
            is_anomaly=anomaly_type is not None,
            anomaly_type=anomaly_type,
            z_score=round(score, 4),
            current_value=value,
            mean=round(mean_pow, 4),
            stdev=round(std_pow, 4),
            sample_count=len(self._window),
        )

    # ------------------------------------------------------------------
    # Non-cyclic fallback
    # ------------------------------------------------------------------

    def _fallback_check(self, value: float) -> AnomalyResult:
        """IQR-based z-score with streak filter for non-cyclic devices."""
        if len(self._window) < self._min_samples:
            return AnomalyResult(
                is_anomaly=False,
                anomaly_type=None,
                z_score=0.0,
                current_value=value,
                mean=0.0,
                stdev=0.0,
                sample_count=len(self._window),
            )

        sorted_w = sorted(self._window)
        n = len(sorted_w)
        q1 = sorted_w[n // 4]
        q3 = sorted_w[3 * n // 4]
        iqr = q3 - q1
        median = statistics.median(self._window)
        scale = max(iqr * _IQR_SCALE, self._min_deviation)

        score = (value - median) / scale
        raw_anomaly = abs(score) >= self._threshold

        if raw_anomaly:
            current_type = "spike" if score > 0 else "drop"
            if self._streak_type == current_type:
                self._streak_count += 1
            else:
                self._streak_type = current_type
                self._streak_count = 1
        else:
            self._streak_type = None
            self._streak_count = 0

        confirmed = raw_anomaly and self._streak_count >= self._consecutive_required
        anomaly_type = self._streak_type if confirmed else None

        return AnomalyResult(
            is_anomaly=confirmed,
            anomaly_type=anomaly_type,
            z_score=round(score, 4),
            current_value=value,
            mean=round(median, 4),
            stdev=round(scale, 4),
            sample_count=len(self._window),
        )

    # ------------------------------------------------------------------
    # Runtime settings update
    # ------------------------------------------------------------------

    def update_settings(
        self,
        window_size: int | None = None,
        threshold: float | None = None,
        min_samples: int | None = None,
        min_deviation: float | None = None,
        consecutive_required: int | None = None,
    ) -> None:
        """Update detector parameters at runtime."""
        if threshold is not None:
            self._threshold = threshold
        if min_samples is not None:
            self._min_samples = min_samples
        if min_deviation is not None:
            self._min_deviation = min_deviation
        if consecutive_required is not None:
            self._consecutive_required = max(1, consecutive_required)
            self._streak_type = None
            self._streak_count = 0
        if window_size is not None and window_size != self._window.maxlen:
            self._window = deque(self._window, maxlen=window_size)
            self._half_cycles = deque(self._half_cycles, maxlen=window_size)
            self._window_size = window_size

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize detector state for persistence."""
        return {
            "window": list(self._window),
            "window_size": self._window.maxlen,
            "threshold": self._threshold,
            "min_samples": self._min_samples,
            "min_deviation": self._min_deviation,
            "consecutive_required": self._consecutive_required,
            # Mode detection
            "mode_threshold": self._mode_threshold,
            "is_cyclic": self._is_cyclic,
            "warmup_complete": self._warmup_complete,
            # State machine
            "current_state": self._current_state,
            "state_start": self._state_start,
            "state_values": list(self._state_values),
            # Half-cycle history
            "half_cycles": [
                {
                    "state": hc.state,
                    "duration": hc.duration,
                    "mean_power": hc.mean_power,
                }
                for hc in self._half_cycles
            ],
            # Non-cyclic streak
            "streak_type": self._streak_type,
            "streak_count": self._streak_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AnomalyDetector:
        """Restore detector from persisted data."""
        detector = cls(
            window_size=data["window_size"],
            threshold=data["threshold"],
            min_samples=data["min_samples"],
            min_deviation=data.get("min_deviation", 5.0),
            consecutive_required=data.get("consecutive_required", 3),
        )
        detector._window.extend(data["window"])
        # Mode detection
        detector._mode_threshold = data.get("mode_threshold")
        detector._is_cyclic = data.get("is_cyclic", False)
        detector._warmup_complete = data.get("warmup_complete", False)
        # State machine — reset state_start to now: avoids stale duration
        # calculations if HA was down for an unknown period.
        detector._current_state = data.get("current_state")
        detector._state_start = time.time()
        detector._state_values = list(data.get("state_values", []))
        # Half-cycle history
        for hc_data in data.get("half_cycles", []):
            detector._half_cycles.append(
                _HalfCycle(
                    state=hc_data["state"],
                    duration=hc_data["duration"],
                    mean_power=hc_data["mean_power"],
                )
            )
        # Non-cyclic streak
        detector._streak_type = data.get("streak_type")
        detector._streak_count = data.get("streak_count", 0)
        return detector
