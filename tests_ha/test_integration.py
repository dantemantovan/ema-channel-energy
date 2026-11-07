"""Runs inside the pytest-homeassistant-custom-component harness (mocked API)."""
from datetime import timedelta
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ema_channel_energy.api import ChannelEnergy, EmaAuthError
from custom_components.ema_channel_energy.const import DOMAIN

DATA = {"app_id": "a" * 32, "app_secret": "s" * 12, "sid": "SID0001", "ecu_id": "216000000000"}
CH = [ChannelEnergy(f"90000000000{i}", c, 1.0 + i / 10 + c / 100)
      for i in range(1, 7) for c in (1, 2)]
P = "custom_components.ema_channel_energy.api.EmaClient.batch_energy"


async def test_flow_success(hass):
    with patch(P, AsyncMock(return_value=CH)) as m, \
         patch("custom_components.ema_channel_energy.async_setup_entry", return_value=True):
        r = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER})
        assert r["type"] is FlowResultType.FORM
        r = await hass.config_entries.flow.async_configure(r["flow_id"], DATA)
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert m.await_count == 1


async def test_flow_auth_error(hass):
    with patch(P, AsyncMock(side_effect=EmaAuthError("code 4000"))):
        r = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER})
        r = await hass.config_entries.flow.async_configure(r["flow_id"], DATA)
    assert r["errors"] == {"base": "invalid_auth"}


async def test_setup_creates_12_channel_sensors_and_no_duplicate_call(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=DATA, unique_id="SID0001_216000000000")
    entry.add_to_hass(hass)
    with patch(P, AsyncMock(return_value=CH)) as m:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        await hass.async_block_till_done()
        assert m.await_count == 1
        states = [s for s in hass.states.async_all("sensor")
                  if "daily_energy" in s.entity_id]
        assert len(states) == 12
        s = states[0]
        assert s.attributes["unit_of_measurement"] == "kWh"
        assert "state_class" not in s.attributes
        yday = (dt_util.now().date() - timedelta(days=1)).isoformat()
        assert s.attributes["data_date"] == yday
        # Reload (simulated restart) must not call again for the same day.
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()
        assert m.await_count == 1
        # Manual refresh is allowed once, then throttled.
        await hass.services.async_call("button", "press", {
            "entity_id": "button.ema_ecu_216000000000_cloud_daily_refresh_previous_day"},
            blocking=True)
        await hass.services.async_call("button", "press", {
            "entity_id": "button.ema_ecu_216000000000_cloud_daily_refresh_previous_day"},
            blocking=True)
        assert m.await_count == 2
    total = hass.states.get(
        "sensor.ema_ecu_216000000000_cloud_daily_previous_day_total_all_channels")
    assert total is not None and float(total.state) > 0
