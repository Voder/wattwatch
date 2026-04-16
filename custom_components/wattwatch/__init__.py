"""WattWatch — Power consumption anomaly detection for Home Assistant."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .coordinator import WattWatchCoordinator

_LOGGER = logging.getLogger(__name__)

type WattWatchConfigEntry = ConfigEntry[WattWatchCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: WattWatchConfigEntry
) -> bool:
    """Set up WattWatch from a config entry."""
    coordinator = WattWatchCoordinator(hass, entry)
    await coordinator.async_start()

    entry.runtime_data = coordinator

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
