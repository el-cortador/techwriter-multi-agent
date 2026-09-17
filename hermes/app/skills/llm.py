from __future__ import annotations

import time

from openai import APIConnectionError, APITimeoutError, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app import config, telemetry
from app.telemetry_context import get_current_run_id

RETRYABLE_LLM_EXCEPTIONS = (RateLimitError, APIConnectionError, APITimeoutError)


class GenerationError(Exception):
    pass


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type(RETRYABLE_LLM_EXCEPTIONS),
)
def create_chat_completion(client, **kwargs):
    return client.chat.completions.create(**kwargs)


def generate_text(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int | None = None,
) -> str:
    if not config.OPENROUTER_API_KEY:
        raise GenerationError("OPENROUTER_API_KEY is not set.")

    from openai import OpenAI

    client = OpenAI(
        api_key=config.OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
        timeout=config.LLM_REQUEST_TIMEOUT,
    )
    started_at = time.time()
    response = create_chat_completion(
        client,
        model=model or config.LLM_MODEL_NAME,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens or config.LLM_MAX_TOKENS,
    )
    finished_at = time.time()
    usage = response.usage
    run_id = get_current_run_id()
    if run_id is not None and usage is not None:
        telemetry.record_llm_call(
            run_id,
            provider="openrouter",
            model_name=response.model or model or config.LLM_MODEL_NAME,
            started_at=started_at,
            finished_at=finished_at,
            prompt_tokens=usage.prompt_tokens or 0,
            completion_tokens=usage.completion_tokens or 0,
            total_tokens=usage.total_tokens or 0,
            raw_response_id=response.id,
            metadata={"temperature": temperature},
        )
    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise GenerationError("LLM returned an empty response.")
    return content
