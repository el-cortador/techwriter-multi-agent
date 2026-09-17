from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import httpx
import requests

from app import http_client


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class HttpClientGetRetryTest(unittest.TestCase):
    @patch("time.sleep", return_value=None)
    @patch("app.http_client.requests.get")
    def test_retries_on_503_then_succeeds(self, requests_get, _sleep) -> None:
        ok = _FakeResponse(200)
        requests_get.side_effect = [_FakeResponse(503), _FakeResponse(503), ok]

        result = http_client.get("https://example.test/x")

        self.assertIs(result, ok)
        self.assertEqual(requests_get.call_count, 3)

    @patch("time.sleep", return_value=None)
    @patch("app.http_client.requests.get")
    def test_retries_on_timeout_then_succeeds(self, requests_get, _sleep) -> None:
        ok = _FakeResponse(200)
        requests_get.side_effect = [requests.Timeout("timed out"), ok]

        result = http_client.get("https://example.test/x")

        self.assertIs(result, ok)
        self.assertEqual(requests_get.call_count, 2)

    @patch("app.http_client.requests.get")
    def test_does_not_retry_on_404(self, requests_get) -> None:
        not_found = _FakeResponse(404)
        requests_get.return_value = not_found

        result = http_client.get("https://example.test/x")

        self.assertIs(result, not_found)
        self.assertEqual(requests_get.call_count, 1)


class HttpxGetRetryTest(unittest.TestCase):
    @patch("time.sleep", return_value=None)
    def test_retries_on_503_then_succeeds(self, _sleep) -> None:
        ok = _FakeResponse(200)
        client = MagicMock()
        client.get.side_effect = [_FakeResponse(503), ok]

        result = http_client.httpx_get(client, "/files/abc")

        self.assertIs(result, ok)
        self.assertEqual(client.get.call_count, 2)

    def test_does_not_retry_on_401(self) -> None:
        unauthorized = _FakeResponse(401)
        client = MagicMock()
        client.get.return_value = unauthorized

        result = http_client.httpx_get(client, "/files/abc")

        self.assertIs(result, unauthorized)
        self.assertEqual(client.get.call_count, 1)

    @patch("time.sleep", return_value=None)
    def test_retries_on_connect_error_then_succeeds(self, _sleep) -> None:
        ok = _FakeResponse(200)
        client = MagicMock()
        client.get.side_effect = [httpx.ConnectError("boom"), ok]

        result = http_client.httpx_get(client, "/files/abc")

        self.assertIs(result, ok)
        self.assertEqual(client.get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
