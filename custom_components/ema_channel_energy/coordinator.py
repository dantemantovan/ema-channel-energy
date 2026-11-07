"""Once-a-day fetch manager for EMA Channel Energy."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_call_later, async_track_time_change
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .api import EmaAuthError, EmaClient, EmaError, EmaLimitError
from .const import (
    CONF_APP_ID,
    CONF_APP_SECRET,
    CONF_ECU_ID,
    CONF_SID,
    DOMAIN,
    FETCH_HOUR,
    FETCH_MINUTE,
    RETRY_DELAY_HOURS,
    STORAGE_VERSION,
)
from .policy import State, record_attempt, record_failure, record_success, should_fetch, target_day

_LOGGER = logging.getLogger(__name__)


def signal_update(entry_id: str) -> str:
    return f"{DOMAIN}_update_{entry_id}"


class EmaDailyManager:
    def __init__(self, hass: HomeAssistant, entry) -> None:
        self.hass, self.entry = hass, entry
        d = entry.data
        self.client = EmaClient(async_get_clientsession(hass), d[CONF_APP_ID],
                                d[CONF_APP_SECRET], d[CONF_SID], d[CONF_ECU_ID])
        self.store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")
        self.state = State()
        self._unsubs: list = []
        self._busy = False
        self.auth_failed = False

    async def async_load(self) -> None:
        self.state = State.from_dict(await self.store.async_load())

    async def async_start(self) -> None:
        self._unsubs.append(async_track_time_change(
            self.hass, self._scheduled, hour=FETCH_HOUR, minute=FETCH_MINUTE,
            second=0))
        # Catch up once at startup only if yesterday's data is missing;
        # persisted attempt counters prevent restart loops from leaking quota.
        self.hass.async_create_task(self.async_fetch(reason="startup"))

    @callback
    def async_stop(self) -> None:
        for u in self._unsubs:
            u()
        self._unsubs.clear()

    async def _scheduled(self, _now) -> None:
        await self.async_fetch(reason="scheduled")

    async def _retry(self, _now) -> None:
        await self.async_fetch(reason="retry")

    async def async_fetch(self, reason: str, manual: bool = False) -> None:
        if self._busy or self.auth_failed:
            return
        now = dt_util.now()
        if not should_fetch(self.state, now, manual=manual):
            _LOGGER.debug("Fetch skipped (%s)", reason)
            return
        self._busy = True
        day = target_day(now)
        record_attempt(self.state, now, manual=manual)
        await self.store.async_save(self.state.to_dict())
        try:
            channels = await self.client.batch_energy(day)
        except EmaAuthError as err:
            record_failure(self.state, now, f"auth: {err}", limit=False)
            self.auth_failed = True
            self.entry.async_start_reauth(self.hass)
        except EmaLimitError as err:
            _LOGGER.warning("EMA API limit reached (%s); pausing 24h", err)
            record_failure(self.state, now, f"limit: {err}", limit=True)
        except EmaError as err:
            _LOGGER.warning("EMA fetch for %s failed: %s", day, err)
            record_failure(self.state, now, str(err), limit=False)
            if not manual:
                self._unsubs.append(async_call_later(
                    self.hass, timedelta(hours=RETRY_DELAY_HOURS), self._retry))
        else:
            record_success(self.state, now, day,
                           {c.key: c.kwh for c in channels})
            _LOGGER.info("EMA channel energy for %s: %d channels", day,
                         len(channels))
        finally:
            self._busy = False
            await self.store.async_save(self.state.to_dict())
            async_dispatcher_send(self.hass, signal_update(self.entry.entry_id))


__all__ = ["EmaDailyManager", "ConfigEntryAuthFailed", "signal_update"]
