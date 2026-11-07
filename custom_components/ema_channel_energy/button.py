from __future__ import annotations

from homeassistant.components.button import ButtonEntity

from .entity import device_info


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([RefreshButton(entry.runtime_data)])


class RefreshButton(ButtonEntity):
    """Manual refresh of the previous day (throttled; uses 1 API call)."""

    _attr_has_entity_name = True
    _attr_name = "Refresh previous day"
    _attr_icon = "mdi:cloud-refresh"

    def __init__(self, mgr) -> None:
        self.mgr = mgr
        self._attr_unique_id = f"{mgr.entry.entry_id}_refresh"
        self._attr_device_info = device_info(mgr.entry)

    async def async_press(self) -> None:
        await self.mgr.async_fetch(reason="manual", manual=True)
