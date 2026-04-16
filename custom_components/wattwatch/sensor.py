"""Diagnostic sensor platform for WattWatch."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import WattWatchConfigEntry
from .anomaly import AnomalyResult
from .const import DOMAIN

SENSOR_TYPES = {
    "z_score": {
        "name_suffix": "z-score",
        "icon": "mdi:chart-bell-curve",
        "unit": None,
    },
    "mean": {
        "name_suffix": "mean",
        "icon": "mdi:chart-line-variant",
        "unit": "W",
    },
    "stdev": {
        "name_suffix": "stdev",
        "icon": "mdi:sigma",
        "unit": "W",
    },
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WattWatchConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up WattWatch diagnostic sensors from config entry."""
    coordinator = entry.runtime_data

    entities = []
    for entity_id in coordinator.monitored_entities:
        for sensor_type in SENSOR_TYPES:
            entities.append(
                WattWatchDiagnosticSensor(coordinator, entity_id, sensor_type)
            )

    async_add_entities(entities)


class WattWatchDiagnosticSensor(SensorEntity):
    """Diagnostic sensor showing z-score, mean, or stdev for a monitored entity."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = True

    def __init__(
        self, coordinator, entity_id: str, sensor_type: str
    ) -> None:
        self._coordinator = coordinator
        self._monitored_entity_id = entity_id
        self._sensor_type = sensor_type
        self._result: AnomalyResult | None = None

        entity_name = entity_id.split(".")[-1]
        type_info = SENSOR_TYPES[sensor_type]

        self._attr_unique_id = (
            f"wattwatch_{entity_name}_{sensor_type}"
        )
        self._attr_name = (
            f"WattWatch {entity_name.replace('_', ' ').title()} {type_info['name_suffix']}"
        )
        self._attr_icon = type_info["icon"]
        self._attr_native_unit_of_measurement = type_info["unit"]

    @property
    def native_value(self) -> float | None:
        """Return sensor value based on type."""
        if self._result is None:
            return None

        if self._sensor_type == "z_score":
            return self._result.z_score
        if self._sensor_type == "mean":
            return self._result.mean
        if self._sensor_type == "stdev":
            return self._result.stdev
        return None

    @property
    def extra_state_attributes(self) -> dict | None:
        """Return sample count."""
        if self._result is None:
            return None
        return {
            "sample_count": self._result.sample_count,
            "monitored_entity": self._monitored_entity_id,
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to coordinator updates."""
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
