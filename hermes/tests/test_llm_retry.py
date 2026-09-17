from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

import httpx2
from openai import APIConnectionError, BadRequestError, RateLimitError

from app.skills.llm import create_chat_completion


def _request() -> httpx2.Request:
    return httpx2.Request("POST", "https://openrouter.ai/api/v1/chat/completions")


class CreateChatCompletionRetryTest(unittest.TestCase):
    @patch("time.sleep", return_value=None)
    def test_retries_on_transient_errors_then_succeeds(self, _sleep) -> None:
        response = object()
        client = MagicMock()
        client.chat.completions.create.side_effect = [
            RateLimitError("rate limited", response=httpx2.Response(429, request=_request()), body=None),
            APIConnectionError(request=_request()),
            response,
        ]

        result = create_chat_completion(client, model="x", messages=[])

        self.assertIs(result, response)
        self.assertEqual(client.chat.completions.create.call_count, 3)

    def test_does_not_retry_on_bad_request(self) -> None:
        client = MagicMock()
        client.chat.completions.create.side_effect = BadRequestError(
            "bad request", response=httpx2.Response(400, request=_request()), body=None
        )

        with self.assertRaises(BadRequestError):
            create_chat_completion(client, model="x", messages=[])

        self.assertEqual(client.chat.completions.create.call_count, 1)


if __name__ == "__main__":
    unittest.main()
