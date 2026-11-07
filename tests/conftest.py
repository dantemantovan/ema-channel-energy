import sys
from pathlib import Path

# Import the pure modules standalone (no Home Assistant needed).
sys.path.insert(0, str(Path(__file__).parents[1] / "custom_components" / "ema_channel_energy"))

import aiohttp
import pytest_asyncio
from aiohttp import web


@pytest_asyncio.fixture
async def aiohttp_client_session_server():
    runners, sessions = [], []

    async def make(handler):
        app = web.Application()
        app.router.add_get(
            "/user/api/v2/systems/{sid}/devices/inverter/batch/energy/{eid}", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        s = aiohttp.ClientSession()
        runners.append(runner)
        sessions.append(s)
        return s, f"http://127.0.0.1:{port}"

    yield make
    for s in sessions:
        await s.close()
    for r in runners:
        await r.cleanup()
