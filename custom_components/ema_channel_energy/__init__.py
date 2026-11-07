"""EMA Channel Energy: daily per-channel kWh from the APsystems EMA OpenAPI."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import EmaDailyManager

PLATFORMS = [Platform.SENSOR, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    mgr = EmaDailyManager(hass, entry)
    await mgr.async_load()
    entry.runtime_data = mgr
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await mgr.async_start()
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    entry.runtime_data.async_stop()
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
