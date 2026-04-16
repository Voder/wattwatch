"""Anomaly detection engine for WattWatch."""

from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass


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
    """Z-score based anomaly detector with sliding window."""

    def __init__(
        self,
        window_size: int = 100,
        threshold: float = 3.0,
        min_samples: int = 10,
    ) -> None:
        self._window: deque[float] = deque(maxlen=window_size)
        self._threshold = threshold
        self._min_samples = min_samples

    @property
    def sample_count(self) -> int:
        """Return number of samples in window."""
        return len(self._window)

    def add_sample(self, value: float) -> AnomalyResult:
        """Add a sample and check for anomaly.

        Computes z-score against current window, then appends value.
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

        mean = statistics.mean(self._window)
        stdev = statistics.stdev(self._window)

        if stdev == 0:
            self._window.append(value)
            return AnomalyResult(
                is_anomaly=False,
                anomaly_type=None,
                z_score=0.0,
                current_value=value,
                mean=mean,
                stdev=0.0,
                sample_count=len(self._window),
            )

        z_score = (value - mean) / stdev
        is_anomaly = abs(z_score) >= self._threshold

        if is_anomaly:
            anomaly_type = "spike" if z_score > 0 else "drop"
        else:
            anomaly_type = None

        self._window.append(value)

        return AnomalyResult(
            is_anomaly=is_anomaly,
            anomaly_type=anomaly_type,
            z_score=round(z_score, 4),
            current_value=value,
            mean=round(mean, 4),
            stdev=round(stdev, 4),
            sample_count=len(self._window),
        )

    def update_settings(
        self,
        window_size: int | None = None,
        threshold: float | None = None,
        min_samples: int | None = None,
    ) -> None:
        """Update detector parameters at runtime."""
        if threshold is not None:
            self._threshold = threshold
        if min_samples is not None:
            self._min_samples = min_samples
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
        }

    @classmethod
    def from_dict(cls, data: dict) -> AnomalyDetector:
        """Restore detector from persisted data."""
        detector = cls(
            window_size=data["window_size"],
            threshold=data["threshold"],
            min_samples=data["min_samples"],
        )
        detector._window.extend(data["window"])
        return detector
