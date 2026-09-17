from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _csv_ints(name: str) -> set[int]:
    raw = os.getenv(name, "")
    values: set[int] = set()
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        values.add(int(item))
    return values


DISCORD_BOT_TOKEN: str = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_ALLOWED_GUILD_IDS: set[int] = _csv_ints("DISCORD_ALLOWED_GUILD_IDS")
DISCORD_ALLOWED_CHANNEL_IDS: set[int] = _csv_ints("DISCORD_ALLOWED_CHANNEL_IDS")
DISCORD_ALLOWED_USER_IDS: set[int] = _csv_ints("DISCORD_ALLOWED_USER_IDS")

OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")
LLM_MODEL_NAME: str = os.getenv("LLM_MODEL_NAME", "deepseek/deepseek-v4-pro")
LLM_MAX_TOKENS: int = int(os.getenv("LLM_MAX_TOKENS", "8192"))
LLM_TEMPERATURE: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))
HERMES_VISION_MODEL: str = os.getenv("HERMES_VISION_MODEL", "google/gemini-2.5-flash")

GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
GITLAB_TOKEN: str = os.getenv("GITLAB_TOKEN", "")
JIRA_EMAIL: str = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN: str = os.getenv("JIRA_API_TOKEN", "")
FIGMA_TOKEN: str = os.getenv("FIGMA_TOKEN", "")
FIGMA_API_BASE: str = os.getenv("FIGMA_API_BASE", "https://api.figma.com/v1")
REQUEST_TIMEOUT: float = float(os.getenv("REQUEST_TIMEOUT", "15"))
LLM_REQUEST_TIMEOUT: float = float(os.getenv("LLM_REQUEST_TIMEOUT", "60"))
RELEASE_NOTES_MAX_TOKENS: int = int(os.getenv("MAX_TOKENS", "4096"))

DATABASE_URL: str = os.getenv("DATABASE_URL", "")
PROJECT_SLUG: str = os.getenv("PROJECT_SLUG", "techwriter-super-agent")
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LLM_COST_INPUT_PER_1M: Decimal = Decimal(os.getenv("LLM_COST_INPUT_PER_1M", "0"))
LLM_COST_OUTPUT_PER_1M: Decimal = Decimal(os.getenv("LLM_COST_OUTPUT_PER_1M", "0"))
VISION_COST_INPUT_PER_1M: Decimal = Decimal(os.getenv("VISION_COST_INPUT_PER_1M", "0"))
VISION_COST_OUTPUT_PER_1M: Decimal = Decimal(os.getenv("VISION_COST_OUTPUT_PER_1M", "0"))

STATE_DIR: Path = Path(os.getenv("HERMES_STATE_DIR", "/app/state"))
STATE_DIR.mkdir(parents=True, exist_ok=True)

_skills_dir_env = os.getenv("HERMES_SKILLS_DIR", "")
SKILLS_DIR: Path = (
    Path(_skills_dir_env)
    if _skills_dir_env
    else Path(__file__).resolve().parents[2] / "runtimes" / "hermes" / "skills"
)
