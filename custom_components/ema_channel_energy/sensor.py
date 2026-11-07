"""Per-channel daily kWh sensors for the previous completed day.

These are snapshot sensors (no state_class), so Home Assistant's Energy
dashboard will not offer them and nothing is double-counted with the local
ECU integration. Each carries the explicit data_date it describes.
"""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import PERCENTAGE, UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .coordinator import signal_update
from .entity import device_info
from .policy import stats


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    mgr = entry.runtime_data
    known: set[str] = set()

    @callback
    def _add_new() -> None:
        new = [k for k in sorted(mgr.state.channels) if k not in known]
        known.update(new)
        if new:
            async_add_entities([ChannelSensor(mgr, k) for k in new])

    async_add_entities([TotalSensor(mgr), SpreadSensor(mgr)])
    _add_new()
    entry.async_on_unload(async_dispatcher_connect(
        hass, signal_update(entry.entry_id), _add_new))


class _Base(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, mgr, key: str) -> None:
        self.mgr = mgr
        self._attr_unique_id = f"{mgr.entry.entry_id}_{key}"
        self._attr_device_info = device_info(mgr.entry)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(async_dispatcher_connect(
            self.hass, signal_update(self.mgr.entry.entry_id),
            self.async_write_ha_state))

    def _common_attrs(self) -> dict:
        s = self.mgr.state
        return {"data_date": s.data_date, "fetched_at": s.fetched_at,
                "last_error": s.last_error, "source": "APsystems EMA OpenAPI"}


class ChannelSensor(_Base):
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 3

    def __init__(self, mgr, key: str) -> None:
        super().__init__(mgr, f"ch_{key}")
        self.key = key
        uid, ch = key.rsplit("-", 1)
        self.uid, self.ch = uid, int(ch)
        self._attr_name = f"Inverter {uid[-4:]} Ch {ch} daily energy"

    @property
    def available(self) -> bool:
        return self.key in self.mgr.state.channels

    @property
    def native_value(self):
        return self.mgr.state.channels.get(self.key)

    @property
    def extra_state_attributes(self):
        st = stats(self.mgr.state.channels)
        v = self.native_value
        dev = (round((v - st["mean"]) / st["mean"] * 100, 1)
               if v is not None and st and st["mean"] > 0 else None)
        return {**self._common_attrs(), "inverter_uid": self.uid,
                "channel": self.ch, "vs_channel_mean_pct": dev}


class TotalSensor(_Base):
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2
    _attr_name = "Previous day total (all channels)"

    def __init__(self, mgr) -> None:
        super().__init__(mgr, "total")

    @property
    def native_value(self):
        return stats(self.mgr.state.channels).get("total")

    @property
    def extra_state_attributes(self):
        st = stats(self.mgr.state.channels)
        return {**self._common_attrs(), "channel_count": st.get("count"),
                "channel_mean_kwh": st.get("mean")}


class SpreadSensor(_Base):
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_icon = "mdi:arrow-expand-vertical"
    _attr_name = "Previous day channel spread"

    def __init__(self, mgr) -> None:
        super().__init__(mgr, "spread")

    @property
    def native_value(self):
        return stats(self.mgr.state.channels).get("spread_pct")

    @property
    def extra_state_attributes(self):
        return {**self._common_attrs(),
                "definition": "(max - min) / mean of channel kWh; comparison "
                              "aid only, not a fault diagnosis"}
