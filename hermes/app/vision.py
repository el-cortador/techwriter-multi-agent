from __future__ import annotations

import base64
import mimetypes
import time

from openai import OpenAI

from app import config, telemetry
from app.models import IncomingAttachment
from app.skills.llm import create_chat_completion
from app.skills.loader import load_instructions
from app.skills.runner import SkillError
from app.telemetry_context import get_current_run_id


def describe_ui_screenshot(attachment: IncomingAttachment, user_text: str) -> str:
    if not config.OPENROUTER_API_KEY:
        raise SkillError("OPENROUTER_API_KEY не задан для обработки изображений.")

    media_type = attachment.content_type or mimetypes.guess_type(attachment.filename)[0] or "image/png"
    encoded = base64.b64encode(attachment.path.read_bytes()).decode("ascii")

    prompt = load_instructions("figma-guide", "instructions-screenshot.md")
    if user_text.strip():
        prompt += f"\nДополнительный запрос пользователя:\n{user_text.strip()}"

    client = OpenAI(
        api_key=config.OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
        timeout=config.LLM_REQUEST_TIMEOUT,
    )
    started_at = time.time()
    response = create_chat_completion(
        client,
        model=config.HERMES_VISION_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{media_type};base64,{encoded}",
                        },
                    },
                ],
            }
        ],
        temperature=0.2,
        max_tokens=4096,
    )
    finished_at = time.time()
    usage = response.usage
    run_id = get_current_run_id()
    if run_id is not None and usage is not None:
        telemetry.record_llm_call(
            run_id,
            provider="openrouter",
            model_name=response.model or config.HERMES_VISION_MODEL,
            started_at=started_at,
            finished_at=finished_at,
            prompt_tokens=usage.prompt_tokens or 0,
            completion_tokens=usage.completion_tokens or 0,
            total_tokens=usage.total_tokens or 0,
            raw_response_id=response.id,
            input_rate_per_million=config.VISION_COST_INPUT_PER_1M,
            output_rate_per_million=config.VISION_COST_OUTPUT_PER_1M,
            metadata={"modality": "vision", "temperature": 0.2},
        )
    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise SkillError("Vision-модель вернула пустой результат.")
    return content
