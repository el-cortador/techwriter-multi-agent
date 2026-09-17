from __future__ import annotations

import unittest

import aiohttp
from aiohttp.test_utils import TestClient, TestServer

from app.healthcheck import build_app


class _StubDiscordClient:
    def __init__(self, ready: bool) -> None:
        self._ready = ready

    def is_ready(self) -> bool:
        return self._ready


class HealthcheckEndpointTest(unittest.IsolatedAsyncioTestCase):
    async def test_returns_200_when_client_is_ready(self) -> None:
        app = build_app(_StubDiscordClient(ready=True))
        async with TestClient(TestServer(app)) as client:
            response = await client.get("/health")
            self.assertEqual(response.status, 200)

    async def test_returns_503_when_client_is_not_ready(self) -> None:
        app = build_app(_StubDiscordClient(ready=False))
        async with TestClient(TestServer(app)) as client:
            response = await client.get("/health")
            self.assertEqual(response.status, 503)


if __name__ == "__main__":
    unittest.main()
