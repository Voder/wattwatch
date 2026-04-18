"""Anomaly detection engine for WattWatch."""

from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass

# Scale factor to make MAD comparable to stdev for Gaussian data:
# stdev ≈ 1.4826 * MAD
_MAD_SCALE = 1.4826


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


class AnomalyDetector:
    """Robust anomaly detector using median + MAD with streak filter.

    Uses median absolute deviation (MAD) instead of mean/stdev — robust to
    bimodal / cyclic loads (e.g. fridges, compressors) where raw z-score
    produces excessive false positives.

    A `min_deviation` floor prevents hypersensitivity during flat periods.
    A `consecutive_required` streak filter suppresses transient spikes by
    requiring N same-direction anomalous samples in a row before firing.
    """

    def __init__(
        self,
        window_size: int = 100,
        threshold: float = 3.0,
        min_samples: int = 10,
        min_deviation: float = 5.0,
        consecutive_required: int = 3,
    ) -> None:
        self._window: deque[float] = deque(maxlen=window_size)
        self._threshold = threshold
        self._min_samples = min_samples
        self._min_deviation = min_deviation
        self._consecutive_required = max(1, consecutive_required)
        self._streak_type: str | None = None
        self._streak_count: int = 0

    @property
    def sample_count(self) -> int:
        """Return number of samples in window."""
        return len(self._window)

    def add_sample(self, value: float) -> AnomalyResult:
        """Add a sample and check for anomaly.

        Computes robust score against current window, then appends value.
        An anomaly is only confirmed after `consecutive_required` same-direction
        raw anomalies in a row.
        """
        if len(self._window) < self._min_samples:
            self._window.append(value)
            return AnomalyResult(
                is_anomaly=False,
                anomaly_type=None,
                z_score=0.0,
                current_value=value,
                mean=0.0,
                stdev=0.0,
                sample_count=len(self._window),
            )

        median = statistics.median(self._window)
        mad = statistics.median(abs(x - median) for x in self._window)
        effective_deviation = max(mad * _MAD_SCALE, self._min_deviation)

        score = (value - median) / effective_deviation
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

        confirmed = (
            raw_anomaly and self._streak_count >= self._consecutive_required
        )
        anomaly_type = self._streak_type if confirmed else None

        self._window.append(value)

        return AnomalyResult(
            is_anomaly=confirmed,
            anomaly_type=anomaly_type,
            z_score=round(score, 4),
            current_value=value,
            mean=round(median, 4),
            stdev=round(effective_deviation, 4),
            sample_count=len(self._window),
        )

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
            # Reset streak to avoid stale counts after config change
            self._streak_type = None
            self._streak_count = 0
        if window_size is not None and window_size != self._window.maxlen:
            new_window: deque[float] = deque(self._window, maxlen=window_size)
            self._window = new_window

    def to_dict(self) -> dict:
        """Serialize detector state for persistence."""
        return {
            "window": list(self._window),
            "window_size": self._window.maxlen,
            "threshold": self._threshold,
            "min_samples": self._min_samples,
            "min_deviation": self._min_deviation,
            "consecutive_required": self._consecutive_required,
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
        detector._streak_type = data.get("streak_type")
        detector._streak_count = data.get("streak_count", 0)
        return detector
