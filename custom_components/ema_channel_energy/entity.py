from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo

from .const import CONF_ECU_ID, DOMAIN


def device_info(entry) -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, entry.data[CONF_ECU_ID])},
                      name=f"EMA ECU {entry.data[CONF_ECU_ID]} (cloud daily)",
                      manufacturer="APsystems", model="EMA OpenAPI")
