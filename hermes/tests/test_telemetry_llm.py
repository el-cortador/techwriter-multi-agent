from __future__ import annotations

import sys
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.skills.llm import GenerationError, generate_text
from app.telemetry_context import reset_current_run_id, set_current_run_id


class LlmTelemetryTest(unittest.TestCase):
    def test_generate_text_records_usage_for_current_run(self) -> None:
        response = SimpleNamespace(
            id="resp_123",
            model="deepseek/deepseek-v4-pro",
            usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18),
            choices=[SimpleNamespace(message=SimpleNamespace(content="hello"))],
        )
        openai_client = MagicMock()
        openai_client.chat.completions.create.return_value = response
        fake_openai = SimpleNamespace(OpenAI=MagicMock(return_value=openai_client))
        token = set_current_run_id(42)
        try:
            with patch("app.config.OPENROUTER_API_KEY", "test-key"):
                with patch.dict(sys.modules, {"openai": fake_openai}):
                    with patch("app.telemetry.record_llm_call") as record_llm_call:
                        result = generate_text([{"role": "user", "content": "Hi"}])
        finally:
            reset_current_run_id(token)

        self.assertEqual(result, "hello")
        record_llm_call.assert_called_once()
        self.assertEqual(record_llm_call.call_args.args[0], 42)
        self.assertEqual(record_llm_call.call_args.kwargs["total_tokens"], 18)

    def test_generate_text_reports_exhausted_token_limit(self) -> None:
        response = SimpleNamespace(
            id="resp_124",
            model="deepseek/deepseek-v4.1-flash",
            usage=None,
            choices=[SimpleNamespace(message=SimpleNamespace(content=""), finish_reason="length")],
        )
        openai_client = MagicMock()
        openai_client.chat.completions.create.return_value = response
        fake_openai = SimpleNamespace(OpenAI=MagicMock(return_value=openai_client))
        with patch("app.config.OPENROUTER_API_KEY", "test-key"):
            with patch.dict(sys.modules, {"openai": fake_openai}):
                with self.assertRaisesRegex(GenerationError, r"max_tokens limit \(4096\)"):
                    generate_text([{"role": "user", "content": "Hi"}], max_tokens=4096)


if __name__ == "__main__":
    unittest.main()
