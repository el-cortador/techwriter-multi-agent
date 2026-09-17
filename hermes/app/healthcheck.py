from __future__ import annotations

import logging
from typing import Protocol

from aiohttp import web

logger = logging.getLogger(__name__)

HEALTH_HOST = "0.0.0.0"
HEALTH_PORT = 8081


class _ReadinessSource(Protocol):
    def is_ready(self) -> bool: ...


DISCORD_CLIENT_KEY: web.AppKey[_ReadinessSource] = web.AppKey("discord_client")


async def _health(request: web.Request) -> web.Response:
    client = request.app[DISCORD_CLIENT_KEY]
    if client.is_ready():
        return web.Response(status=200, text="ok")
    return web.Response(status=503, text="not ready")


def build_app(client: _ReadinessSource) -> web.Application:
    app = web.Application()
    app[DISCORD_CLIENT_KEY] = client
    app.router.add_get("/health", _health)
    return app


async def start_healthcheck_server(
    client: _ReadinessSource, host: str = HEALTH_HOST, port: int = HEALTH_PORT
) -> web.AppRunner:
    runner = web.AppRunner(build_app(client))
    await runner.setup()
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("Healthcheck endpoint listening on %s:%s/health", host, port, extra={"service": "hermes-discord"})
    return runner
