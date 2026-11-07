"""Minimal async client for the official APsystems EMA OpenAPI.

Only the documented ECU batch-energy endpoint is used:
GET /user/api/v2/systems/{sid}/devices/inverter/batch/energy/{eid}
    ?energy_level=energy&date_range=yyyy-MM-dd
Signing follows manual section 2.2 (HmacSHA256 over
timestamp/nonce/appId/<last path segment>/GET/HmacSHA256, Base64).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import re
import time
import uuid
from dataclasses import dataclass
from datetime import date

import aiohttp

try:  # package import (Home Assistant)
    from .const import API_LIMIT_CODES, AUTH_ERROR_CODES, BASE_URL, CODE_OK, REQUEST_TIMEOUT_S
except ImportError:  # standalone import in tests
    from const import API_LIMIT_CODES, AUTH_ERROR_CODES, BASE_URL, CODE_OK, REQUEST_TIMEOUT_S  # type: ignore

_ID_RE = re.compile(r"^[A-Za-z0-9]{4,64}$")


class EmaError(Exception):
    """Generic API/transport error."""


class EmaAuthError(EmaError):
    """Credentials rejected."""


class EmaLimitError(EmaError):
    """Monthly quota or rate limit reached."""


class EmaResponseError(EmaError):
    """Unexpected response shape."""


def sign(app_id: str, app_secret: str, last_segment: str, timestamp: str,
         nonce: str, method: str = "GET") -> str:
    """Return the Base64 HmacSHA256 signature defined by the manual."""
    to_sign = f"{timestamp}/{nonce}/{app_id}/{last_segment}/{method}/HmacSHA256"
    digest = hmac.new(app_secret.encode("utf-8"), to_sign.encode("utf-8"),
                      hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")


@dataclass(frozen=True)
class ChannelEnergy:
    inverter_uid: str
    channel: int
    kwh: float

    @property
    def key(self) -> str:
        return f"{self.inverter_uid}-{self.channel}"


def parse_batch_energy(payload: object) -> list[ChannelEnergy]:
    """Parse {"code":0,"data":{"energy":["<uid>-<ch>-<kWh>", ...]}}."""
    if not isinstance(payload, dict):
        raise EmaResponseError("response is not an object")
    code = payload.get("code")
    if code in AUTH_ERROR_CODES:
        raise EmaAuthError(f"API code {code}")
    if code in API_LIMIT_CODES:
        raise EmaLimitError(f"API code {code}")
    if code != CODE_OK:
        raise EmaError(f"API code {code}")
    data = payload.get("data")
    items = data.get("energy") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise EmaResponseError("missing data.energy list")
    out: dict[str, ChannelEnergy] = {}
    for raw in items:
        if not isinstance(raw, str):
            raise EmaResponseError("energy item is not a string")
        parts = raw.split("-")
        if len(parts) != 3:
            raise EmaResponseError("energy item not uid-channel-kWh")
        uid, ch, kwh = parts
        try:
            ce = ChannelEnergy(uid, int(ch), float(kwh))
        except ValueError as err:
            raise EmaResponseError("energy item has non-numeric parts") from err
        if not _ID_RE.match(uid) or ce.channel < 1 or ce.kwh < 0:
            raise EmaResponseError("energy item out of range")
        out[ce.key] = ce  # duplicates: last one wins
    return sorted(out.values(), key=lambda c: (c.inverter_uid, c.channel))


class EmaClient:
    def __init__(self, session: aiohttp.ClientSession, app_id: str,
                 app_secret: str, sid: str, ecu_id: str) -> None:
        for v in (sid, ecu_id):
            if not _ID_RE.match(v):
                raise ValueError("invalid SID/ECU id")
        self._s, self._app, self._sec = session, app_id, app_secret
        self._sid, self._ecu = sid, ecu_id

    async def batch_energy(self, day: date) -> list[ChannelEnergy]:
        path = (f"/user/api/v2/systems/{self._sid}/devices/inverter/"
                f"batch/energy/{self._ecu}")
        ts = str(int(time.time() * 1000))
        nonce = uuid.uuid4().hex
        headers = {
            "X-CA-AppId": self._app,
            "X-CA-Timestamp": ts,
            "X-CA-Nonce": nonce,
            "X-CA-Signature-Method": "HmacSHA256",
            "X-CA-Signature": sign(self._app, self._sec, self._ecu, ts, nonce),
        }
        params = {"energy_level": "energy", "date_range": day.isoformat()}
        try:
            async with self._s.get(
                BASE_URL + path, params=params, headers=headers,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_S),
            ) as resp:
                if resp.status in (401, 403):
                    raise EmaAuthError(f"HTTP {resp.status}")
                if resp.status == 429:
                    raise EmaLimitError("HTTP 429")
                if resp.status != 200:
                    raise EmaError(f"HTTP {resp.status}")
                text = await resp.text()
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise EmaError(f"transport: {type(err).__name__}") from err
        try:
            payload = json.loads(text.lstrip("\ufeff"))
        except ValueError as err:
            raise EmaResponseError("invalid JSON") from err
        return parse_batch_energy(payload)
