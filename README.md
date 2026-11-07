# EMA Channel Energy (Home Assistant custom integration)

Fetches **yesterday's per-channel (per-panel) energy** for an APsystems ECU from the
official **APsystems EMA OpenAPI**, once a day, and exposes one sensor per inverter channel.

It is designed to sit **alongside** a local ECU integration (e.g. `apsystems_ecur`):
keep the local integration for live data and the Energy dashboard; use this one for
day-by-day channel comparison.

## What you get
- `Inverter XXXX Ch N daily energy` (kWh) for every channel the API returns, created dynamically.
  Attributes: `data_date` (the day the value describes), `inverter_uid`, `channel`,
  `vs_channel_mean_pct`, `fetched_at`, `last_error`.
- `Previous day total (all channels)` (kWh) and `Previous day channel spread` (%), defined as
  (max − min) / mean of channel kWh. A comparison aid, **not** a fault diagnosis
  (shade, orientation and panel rating all affect it).
- Button `Refresh previous day` (throttled to once per 15 min, uses 1 API call).

The energy sensors have **no `state_class`**, so the Energy dashboard will not offer them and
nothing is double-counted. Past days are not back-filled into Home Assistant history.

## API usage
Only `GET /user/api/v2/systems/{sid}/devices/inverter/batch/energy/{ecu}?energy_level=energy`
is called, against the fixed official base URL `https://api.apsystemsema.com:9282`.

- 1 call when adding the integration (credential validation) and 1 at startup if yesterday's
  data is not already stored.
- 1 call per day at 00:45 local time for the previous day (≈30–31 calls/month).
- On failure: retry after 2 h, at most 3 attempts per target day (counted across restarts).
- On quota / rate-limit responses (codes 2005, 7001–7003 or HTTP 429): pause 24 h.
- On auth rejection (code 4000 / HTTP 401/403): stop and ask for re-authentication.

Data and attempt counters are kept in `.storage/ema_channel_energy.<entry_id>`.

## Install
HACS → Custom repositories → add this repo (type *Integration*), download, restart Home
Assistant, then Settings → Devices & services → Add integration → **EMA Channel Energy**.
Or copy `custom_components/ema_channel_energy` into your `config/custom_components/`.

You need from EMA: **App ID**, **App Secret** (EMA → Settings → OpenAPI Service),
**SID** (Settings → Account details) and your **ECU ID**.

## Development
```
pip install pytest pytest-asyncio aiohttp ruff
ruff check . && pytest
```
Tests use a synthetic batch-energy response (fake inverter IDs and made-up kWh values, same schema as the real API) and mock HTTP; they do not prove
runtime behaviour inside Home Assistant.

Not affiliated with APsystems.
