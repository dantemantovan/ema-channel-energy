"""Config flow: validates credentials with one batch-energy call."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType
from homeassistant.util import dt as dt_util

from .api import EmaAuthError, EmaClient, EmaError, EmaLimitError
from .const import CONF_APP_ID, CONF_APP_SECRET, CONF_ECU_ID, CONF_SID, DOMAIN
from .policy import target_day

_LOGGER = logging.getLogger(__name__)
_PW = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


def _schema(d: dict) -> vol.Schema:
    return vol.Schema({
        vol.Required(CONF_APP_ID, default=d.get(CONF_APP_ID, "")): str,
        vol.Required(CONF_APP_SECRET): _PW,
        vol.Required(CONF_SID, default=d.get(CONF_SID, "")): str,
        vol.Required(CONF_ECU_ID, default=d.get(CONF_ECU_ID, "")): str,
    })


async def _validate(hass, data: dict) -> str | None:
    try:
        client = EmaClient(async_get_clientsession(hass), data[CONF_APP_ID].strip(),
                           data[CONF_APP_SECRET].strip(), data[CONF_SID].strip(),
                           data[CONF_ECU_ID].strip())
        chans = await client.batch_energy(target_day(dt_util.now()))
    except ValueError:
        return "invalid_id"
    except EmaAuthError:
        return "invalid_auth"
    except EmaLimitError:
        return "rate_limited"
    except EmaError as err:
        _LOGGER.debug("validation failed: %s", err)
        return "cannot_connect"
    return None if chans else "no_channels"


class EmaChannelEnergyFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None
                              ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input = {k: v.strip() for k, v in user_input.items()}
            await self.async_set_unique_id(
                f"{user_input[CONF_SID]}_{user_input[CONF_ECU_ID]}")
            self._abort_if_unique_id_configured()
            if (err := await _validate(self.hass, user_input)) is None:
                return self.async_create_entry(
                    title=f"EMA channels (ECU …{user_input[CONF_ECU_ID][-4:]})",
                    data=user_input)
            errors["base"] = err
        return self.async_show_form(step_id="user",
                                    data_schema=_schema(user_input or {}),
                                    errors=errors)

    async def async_step_reauth(self, entry_data: dict[str, Any]
                                ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None
                                        ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data = {**entry.data, **{k: v.strip() for k, v in user_input.items()}}
            if (err := await _validate(self.hass, data)) is None:
                return self.async_update_reload_and_abort(entry, data=data)
            errors["base"] = err
        return self.async_show_form(
            step_id="reauth_confirm", errors=errors,
            data_schema=vol.Schema({
                vol.Required(CONF_APP_ID, default=entry.data[CONF_APP_ID]): str,
                vol.Required(CONF_APP_SECRET): _PW}))
