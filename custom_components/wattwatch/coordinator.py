"""Event-driven coordinator for WattWatch."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Callable

from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store

from .anomaly import AnomalyDetector, AnomalyResult
from .const import (
    ANOMALY_TYPES_HIGH,
    ANOMALY_TYPES_LOW,
    CONF_CONSECUTIVE_REQUIRED,
    CONF_COOLDOWN,
    CONF_ENTITIES,
    CONF_MIN_DEVIATION,
    CONF_MIN_SAMPLES,
    CONF_MONITOR_DIRECTIONS,
    CONF_THRESHOLD,
    CONF_WINDOW_SIZE,
    DEFAULT_CONSECUTIVE_REQUIRED,
    DEFAULT_COOLDOWN,
    DEFAULT_DIRECTION,
    DEFAULT_MIN_DEVIATION,
    DEFAULT_MIN_SAMPLES,
    DEFAULT_THRESHOLD,
    DEFAULT_WINDOW_SIZE,
    DIRECTION_HIGH,
    DIRECTION_LOW,
    EVENT_ANOMALY_DETECTED,
    STORAGE_KEY,
    STORAGE_VERSION,
)

if TYPE_CHECKING:
    from datetime import timedelta

    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

PERSIST_INTERVAL = 300  # 5 minutes


class WattWatchCoordinator:
    """Coordinate anomaly detection across monitored entities."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self._detectors: dict[str, AnomalyDetector] = {}
        self._anomaly_states: dict[str, AnomalyResult | None] = {}
        self._cooldowns: dict[str, float] = {}
        self._listeners: list[Callable[[str, AnomalyResult], None]] = []
        self._unsub_callbacks: list[CALLBACK_TYPE] = []
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)

    @property
    def monitored_entities(self) -> list[str]:
        """Return list of monitored entity IDs."""
        return self.entry.options.get(CONF_ENTITIES, [])

    @property
    def _threshold(self) -> float:
        return self.entry.options.get(CONF_THRESHOLD, DEFAULT_THRESHOLD)

    @property
    def _window_size(self) -> int:
        return self.entry.options.get(CONF_WINDOW_SIZE, DEFAULT_WINDOW_SIZE)

    @property
    def _min_samples(self) -> int:
        return self.entry.options.get(CONF_MIN_SAMPLES, DEFAULT_MIN_SAMPLES)

    @property
    def _cooldown(self) -> int:
        return self.entry.options.get(CONF_COOLDOWN, DEFAULT_COOLDOWN)

    @property
    def _min_deviation(self) -> float:
        return self.entry.options.get(CONF_MIN_DEVIATION, DEFAULT_MIN_DEVIATION)

    @property
    def _consecutive_required(self) -> int:
        return self.entry.options.get(
            CONF_CONSECUTIVE_REQUIRED, DEFAULT_CONSECUTIVE_REQUIRED
        )

    def get_direction(self, entity_id: str) -> str:
        """Return monitor direction for an entity."""
        directions = self.entry.options.get(CONF_MONITOR_DIRECTIONS, {})
        return directions.get(entity_id, DEFAULT_DIRECTION)

    def _is_anomaly_for_direction(
        self, entity_id: str, result: AnomalyResult
    ) -> bool:
        """Check if anomaly matches configured direction for entity."""
        if not result.is_anomaly:
            return False
        direction = self.get_direction(entity_id)
        if direction == DIRECTION_HIGH:
            return result.anomaly_type in ANOMALY_TYPES_HIGH
        if direction == DIRECTION_LOW:
            return result.anomaly_type in ANOMALY_TYPES_LOW
        return True  # "both"

    async def async_start(self) -> None:
        """Start monitoring: restore state, subscribe to changes."""
        await self._async_restore_detectors()

        # Ensure detectors exist for all monitored entities
        for entity_id in self.monitored_entities:
            if entity_id not in self._detectors:
                self._detectors[entity_id] = AnomalyDetector(
                    window_size=self._window_size,
                    threshold=self._threshold,
                    min_samples=self._min_samples,
                    min_deviation=self._min_deviation,
                    consecutive_required=self._consecutive_required,
                )
            else:
                # Apply current options to restored detectors
                self._detectors[entity_id].update_settings(
                    window_size=self._window_size,
                    threshold=self._threshold,
                    min_samples=self._min_samples,
                    min_deviation=self._min_deviation,
                    consecutive_required=self._consecutive_required,
                )

        # Subscribe to state changes
        if self.monitored_entities:
            unsub = async_track_state_change_event(
                self.hass,
                self.monitored_entities,
                self._handle_state_change,
            )
            self._unsub_callbacks.append(unsub)

        # Periodic persistence
        from datetime import timedelta

        unsub_timer = async_track_time_interval(
            self.hass,
            self._async_persist_callback,
            timedelta(seconds=PERSIST_INTERVAL),
        )
        self._unsub_callbacks.append(unsub_timer)

        # Persist on shutdown
        unsub_stop = self.hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STOP, self._async_on_stop
        )
        self._unsub_callbacks.append(unsub_stop)

        _LOGGER.debug(
            "WattWatch started monitoring %d entities", len(self.monitored_entities)
        )

    async def async_stop(self) -> None:
        """Stop monitoring and persist state."""
        for unsub in self._unsub_callbacks:
            unsub()
        self._unsub_callbacks.clear()

        await self._async_persist()
        _LOGGER.debug("WattWatch stopped")

    @callback
    def _handle_state_change(self, event: Event[EventStateChangedData]) -> None:
        """Handle state change for a monitored entity."""
        entity_id = event.data["entity_id"]
        new_state = event.data["new_state"]

        if new_state is None:
            return
        if new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        try:
            value = float(new_state.state)
        except (ValueError, TypeError):
            return

        detector = self._detectors.get(entity_id)
        if detector is None:
            return

        result = detector.add_sample(value, new_state.last_changed.timestamp())

        # Apply direction filter: replace is_anomaly based on configured direction
        direction_match = self._is_anomaly_for_direction(entity_id, result)
        if result.is_anomaly and not direction_match:
            # Anomaly detected but not for configured direction — mask it
            result = AnomalyResult(
                is_anomaly=False,
                anomaly_type=None,
                z_score=result.z_score,
                current_value=result.current_value,
                mean=result.mean,
                stdev=result.stdev,
                sample_count=result.sample_count,
            )

        self._anomaly_states[entity_id] = result

        # Fire event with cooldown
        if result.is_anomaly:
            now = time.monotonic()
            last_fire = self._cooldowns.get(entity_id, 0.0)
            if now - last_fire >= self._cooldown:
                self._cooldowns[entity_id] = now
                self.hass.bus.async_fire(
                    EVENT_ANOMALY_DETECTED,
                    {
                        "entity_id": entity_id,
                        "current_value": result.current_value,
                        "expected_value": result.mean,
                        "z_score": result.z_score,
                        "anomaly_type": result.anomaly_type,
                        "stdev": result.stdev,
                    },
                )
                _LOGGER.info(
                    "Anomaly detected for %s: %s (z=%.2f)",
                    entity_id,
                    result.anomaly_type,
                    result.z_score,
                )

        # Notify listeners (binary sensors, diagnostic sensors)
        for listener in self._listeners:
            listener(entity_id, result)

    def get_anomaly_state(self, entity_id: str) -> AnomalyResult | None:
        """Get latest anomaly result for an entity."""
        return self._anomaly_states.get(entity_id)

    @callback
    def register_listener(
        self, listener: Callable[[str, AnomalyResult], None]
    ) -> CALLBACK_TYPE:
        """Register a listener for anomaly state changes. Returns unsub callable."""
        self._listeners.append(listener)

        @callback
        def remove_listener() -> None:
            self._listeners.remove(listener)

        return remove_listener

    async def _async_restore_detectors(self) -> None:
        """Restore detector states from storage."""
        stored = await self._store.async_load()
        if not stored or "detectors" not in stored:
            return

        for entity_id, data in stored["detectors"].items():
            try:
                self._detectors[entity_id] = AnomalyDetector.from_dict(data)
                _LOGGER.debug(
                    "Restored detector for %s (%d samples)",
                    entity_id,
                    len(data.get("window", [])),
                )
            except (KeyError, TypeError, ValueError) as err:
                _LOGGER.warning(
                    "Failed to restore detector for %s: %s", entity_id, err
                )

    async def _async_persist(self) -> None:
        """Persist detector states to storage."""
        data: dict[str, Any] = {
            "detectors": {
                entity_id: detector.to_dict()
                for entity_id, detector in self._detectors.items()
                if entity_id in self.monitored_entities
            }
        }
        await self._store.async_save(data)
        _LOGGER.debug("Persisted %d detectors", len(data["detectors"]))

    async def _async_persist_callback(self, _now: Any = None) -> None:
        """Periodic persistence callback."""
        await self._async_persist()

    async def _async_on_stop(self, _event: Event) -> None:
        """Handle HA stop event."""
        await self._async_persist()
