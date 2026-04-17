"""WattWatch — Power consumption anomaly detection for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import DIAGNOSTIC_SENSOR_TYPES, DOMAIN, PLATFORMS
from .coordinator import WattWatchCoordinator

_LOGGER = logging.getLogger(__name__)

type WattWatchConfigEntry = ConfigEntry[WattWatchCoordinator]


@callback
def _async_cleanup_orphaned_entities(
    hass: HomeAssistant,
    entry: WattWatchConfigEntry,
    monitored_entities: list[str],
) -> None:
    """Remove entity registry entries for entities no longer monitored."""
    registry = er.async_get(hass)

    valid_unique_ids: set[str] = set()
    for entity_id in monitored_entities:
        name = entity_id.split(".")[-1]
        valid_unique_ids.add(f"wattwatch_{name}_anomaly")
        for sensor_type in DIAGNOSTIC_SENSOR_TYPES:
            valid_unique_ids.add(f"wattwatch_{name}_{sensor_type}")

    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg_entry.unique_id not in valid_unique_ids:
            _LOGGER.debug("Removing orphaned entity %s", reg_entry.entity_id)
            registry.async_remove(reg_entry.entity_id)


async def async_setup_entry(
    hass: HomeAssistant, entry: WattWatchConfigEntry
) -> bool:
    """Set up WattWatch from a config entry."""
    coordinator = WattWatchCoordinator(hass, entry)
    await coordinator.async_start()

    entry.runtime_data = coordinator

    _async_cleanup_orphaned_entities(hass, entry, coordinator.monitored_entities)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(
        entry.add_update_listener(_async_update_options)
    )

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: WattWatchConfigEntry
) -> bool:
    """Unload WattWatch config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        await entry.runtime_data.async_stop()

    return unload_ok


async def _async_update_options(
    hass: HomeAssistant, entry: WattWatchConfigEntry
) -> None:
    """Handle options update by reloading the entry."""
    await hass.config_entries.async_reload(entry.entry_id)
