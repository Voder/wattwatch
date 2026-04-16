"""Binary sensor platform for WattWatch anomaly detection."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import WattWatchConfigEntry
from .anomaly import AnomalyResult
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WattWatchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up WattWatch binary sensors from config entry."""
    coordinator = entry.runtime_data

    async_add_entities(
        WattWatchAnomalySensor(coordinator, entity_id)
        for entity_id in coordinator.monitored_entities
    )


class WattWatchAnomalySensor(BinarySensorEntity):
    """Binary sensor indicating anomaly state for a monitored power entity."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_has_entity_name = True

    def __init__(self, coordinator, entity_id: str) -> None:
        self._coordinator = coordinator
        self._monitored_entity_id = entity_id
        self._result: AnomalyResult | None = None

        # Derive a clean name from the entity ID
        entity_name = entity_id.split(".")[-1]
        self._attr_unique_id = f"wattwatch_{entity_name}_anomaly"
        self._attr_name = f"WattWatch {entity_name.replace('_', ' ').title()} anomaly"

    @property
    def is_on(self) -> bool | None:
        """Return True if anomaly detected."""
        if self._result is None:
            return None
        return self._result.is_anomaly

    @property
    def extra_state_attributes(self) -> dict | None:
        """Return additional anomaly details."""
        if self._result is None:
            return None
        return {
            "z_score": self._result.z_score,
            "anomaly_type": self._result.anomaly_type,
            "current_value": self._result.current_value,
            "expected_value": self._result.mean,
            "stdev": self._result.stdev,
            "sample_count": self._result.sample_count,
            "monitored_entity": self._monitored_entity_id,
            "monitor_direction": self._coordinator.get_direction(
                self._monitored_entity_id
            ),
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator updates."""
        # Get current state if available
        self._result = self._coordinator.get_anomaly_state(
            self._monitored_entity_id
        )

        @callback
        def _handle_update(entity_id: str, result: AnomalyResult) -> None:
            if entity_id == self._monitored_entity_id:
                self._result = result
                self.async_write_ha_state()

        self.async_on_remove(
            self._coordinator.register_listener(_handle_update)
        )
