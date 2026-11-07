import json
from datetime import date
from pathlib import Path

import pytest
from aiohttp import web

import api
from api import (
    EmaAuthError,
    EmaClient,
    EmaError,
    EmaLimitError,
    EmaResponseError,
    parse_batch_energy,
    sign,
)

FIX = json.loads((Path(__file__).parent / "fixtures" / "batch_energy_day.json").read_text())


def test_signature_vector():
    # Expected value computed independently with `openssl dgst -sha256 -hmac`.
    assert sign("testappid0000000000000000000000", "testsecret12", "216000000000",
                "1700000000000", "5e36eab8295911ee90751eff13c2920b") == \
        "XQUrk0zNqHjxbyAIsIiip98NAhLvrbIYtmlcRFck0xg="


def test_parse_fixture_12_channels():
    ch = parse_batch_energy(FIX)
    assert len(ch) == 12
    assert {c.channel for c in ch} == {1, 2}
    assert len({c.inverter_uid for c in ch}) == 6
    first = ch[0]
    assert (first.inverter_uid, first.channel, first.kwh) == ("900000000001", 1, 1.01)
    assert round(sum(c.kwh for c in ch), 3) == 12.45


def test_parse_missing_channel_and_duplicates():
    p = {"code": 0, "data": {"energy": ["900000000001-1-1.0", "900000000001-1-2.0"]}}
    ch = parse_batch_energy(p)
    assert len(ch) == 1 and ch[0].kwh == 2.0


@pytest.mark.parametrize("payload,exc", [
    ({"code": 4000}, EmaAuthError),
    ({"code": 7001}, EmaLimitError),
    ({"code": 2005}, EmaLimitError),
    ({"code": 1001}, EmaError),
    ({"code": 0}, EmaResponseError),
    ({"code": 0, "data": {"energy": "x"}}, EmaResponseError),
    ({"code": 0, "data": {"energy": ["bad"]}}, EmaResponseError),
    ({"code": 0, "data": {"energy": ["9000-x-1.0"]}}, EmaResponseError),
    ({"code": 0, "data": {"energy": ["9000-1--1.0"]}}, EmaResponseError),
    ([], EmaResponseError),
])
def test_parse_errors(payload, exc):
    with pytest.raises(exc):
        parse_batch_energy(payload)


def test_client_rejects_bad_ids():
    with pytest.raises(ValueError):
        EmaClient(None, "a", "b", "../x", "1234")




@pytest.mark.asyncio
async def test_client_request_shape(aiohttp_client_session_server, monkeypatch):
    seen = {}

    async def handler(req):
        seen.update(path=req.path, q=dict(req.query), h=dict(req.headers))
        return web.Response(text="\ufeff" + json.dumps(FIX),
                            content_type="application/octet-stream")

    session, base = await aiohttp_client_session_server(handler)
    monkeypatch.setattr(api, "BASE_URL", base)
    c = EmaClient(session, "testappid0000000000000000000000", "testsecret12",
                  "SID123", "216000000000")
    ch = await c.batch_energy(date(2026, 11, 5))
    assert len(ch) == 12
    assert seen["path"].endswith("/systems/SID123/devices/inverter/batch/energy/216000000000")
    assert seen["q"] == {"energy_level": "energy", "date_range": "2026-11-05"}
    h = seen["h"]
    assert h["X-CA-Signature-Method"] == "HmacSHA256"
    assert h["X-CA-Signature"] == sign("testappid0000000000000000000000", "testsecret12",
                                       "216000000000", h["X-CA-Timestamp"], h["X-CA-Nonce"])


@pytest.mark.asyncio
@pytest.mark.parametrize("status,exc", [(401, EmaAuthError), (429, EmaLimitError), (500, EmaError)])
async def test_client_http_errors(aiohttp_client_session_server, monkeypatch, status, exc):
    async def handler(req):
        return web.Response(status=status)
    session, base = await aiohttp_client_session_server(handler)
    monkeypatch.setattr(api, "BASE_URL", base)
    c = EmaClient(session, "a" * 32, "s" * 12, "SID123", "216000000000")
    with pytest.raises(exc):
        await c.batch_energy(date(2026, 11, 5))


@pytest.mark.asyncio
async def test_client_invalid_json(aiohttp_client_session_server, monkeypatch):
    async def handler(req):
        return web.Response(text="<html>")
    session, base = await aiohttp_client_session_server(handler)
    monkeypatch.setattr(api, "BASE_URL", base)
    c = EmaClient(session, "a" * 32, "s" * 12, "SID123", "216000000000")
    with pytest.raises(EmaResponseError):
        await c.batch_energy(date(2026, 11, 5))
