from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config

from app import config

logger = logging.getLogger(__name__)


def _alembic_config() -> Config:
    ini_path = Path("/app/db/alembic.ini")
    if not ini_path.exists():
        ini_path = Path(__file__).resolve().parents[2] / "db" / "alembic.ini"
    # No file_= here on purpose: passing the ini path makes Alembic's env.py call
    # logging.config.fileConfig() on it, which resets the root logger (and its level
    # to WARNING) for the whole process — silently killing our own JSON logging for
    # everything logged after startup. script_location is the only setting we need.
    config = Config()
    config.set_main_option("script_location", str(ini_path.parent / "migrations"))
    return config


def is_enabled() -> bool:
    return bool(config.DATABASE_URL)


def initialize() -> None:
    if not is_enabled():
        logger.warning("Telemetry database disabled: DATABASE_URL is not set")
        return
    last_error: Exception | None = None
    for attempt in range(10):
        try:
            command.upgrade(_alembic_config(), "head")
            return
        except Exception as exc:
            last_error = exc
            logger.warning("Telemetry init failed on attempt %s/10: %s", attempt + 1, exc)
            time.sleep(2)
    raise RuntimeError("Failed to initialize telemetry database") from last_error


@dataclass(frozen=True)
class SessionHandle:
    id: int
    external_session_id: str


@dataclass(frozen=True)
class RunHandle:
    id: int
    session_id: int
    started_at: datetime


def ensure_session(
    *,
    source: str,
    external_session_id: str,
    guild_id: str | None,
    channel_id: str | None,
    user_id: str | None,
    metadata: dict[str, Any] | None = None,
) -> SessionHandle | None:
    if not is_enabled():
        return None
    dict_row = _dict_row()
    with _connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO sessions (
                    project_slug,
                    source,
                    external_session_id,
                    guild_id,
                    channel_id,
                    user_id,
                    metadata_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (project_slug, source, external_session_id)
                DO UPDATE SET
                    guild_id = EXCLUDED.guild_id,
                    channel_id = EXCLUDED.channel_id,
                    user_id = EXCLUDED.user_id,
                    last_activity_at = NOW(),
                    metadata_json = sessions.metadata_json || EXCLUDED.metadata_json
                RETURNING id, external_session_id
                """,
                (
                    config.PROJECT_SLUG,
                    source,
                    external_session_id,
                    guild_id,
                    channel_id,
                    user_id,
                    _to_json(metadata or {}),
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return SessionHandle(id=row["id"], external_session_id=row["external_session_id"])


def start_run(
    *,
    session_id: int,
    source: str,
    route_kind: str,
    model_name: str,
    provider: str,
    temperature: float,
    input_chars: int,
    metadata: dict[str, Any] | None = None,
) -> RunHandle | None:
    if not is_enabled():
        return None
    dict_row = _dict_row()
    with _connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                INSERT INTO runs (
                    session_id,
                    project_slug,
                    source,
                    route_kind,
                    model_name,
                    provider,
                    temperature,
                    input_chars,
                    metadata_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id, session_id, started_at
                """,
                (
                    session_id,
                    config.PROJECT_SLUG,
                    source,
                    route_kind,
                    model_name,
                    provider,
                    temperature,
                    input_chars,
                    _to_json(metadata or {}),
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return RunHandle(id=row["id"], session_id=row["session_id"], started_at=row["started_at"])


def add_attachment(
    run_id: int,
    *,
    filename: str,
    content_type: str | None,
    path: Path,
) -> None:
    if not is_enabled():
        return
    size_bytes = path.stat().st_size if path.exists() else None
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO attachments (run_id, filename, content_type, size_bytes, storage_path)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (run_id, filename, content_type, size_bytes, str(path)),
            )
        conn.commit()


def record_event(run_id: int | None, event_type: str, payload: dict[str, Any] | None = None) -> None:
    if not is_enabled():
        return
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO events (run_id, project_slug, event_type, payload_json)
                VALUES (%s, %s, %s, %s::jsonb)
                """,
                (run_id, config.PROJECT_SLUG, event_type, _to_json(payload or {})),
            )
        conn.commit()


def complete_run(
    run_id: int,
    *,
    started_at: datetime,
    output_chars: int,
    status: str,
    error_message: str | None = None,
) -> None:
    if not is_enabled():
        return
    finished_at = _utcnow()
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE runs
                SET finished_at = %s,
                    duration_ms = %s,
                    output_chars = %s,
                    status = %s,
                    error_message = %s
                WHERE id = %s
                """,
                (finished_at, duration_ms, output_chars, status, error_message, run_id),
            )
            cur.execute(
                """
                UPDATE sessions
                SET last_activity_at = NOW()
                WHERE id = (SELECT session_id FROM runs WHERE id = %s)
                """,
                (run_id,),
            )
        conn.commit()


def record_llm_call(
    run_id: int,
    *,
    provider: str,
    model_name: str,
    started_at: float,
    finished_at: float,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    raw_response_id: str | None,
    input_rate_per_million: Decimal | None = None,
    output_rate_per_million: Decimal | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if not is_enabled():
        return
    input_cost = _cost_for_tokens(prompt_tokens, input_rate_per_million or config.LLM_COST_INPUT_PER_1M)
    output_cost = _cost_for_tokens(completion_tokens, output_rate_per_million or config.LLM_COST_OUTPUT_PER_1M)
    total_cost = input_cost + output_cost
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO llm_calls (
                    run_id,
                    project_slug,
                    provider,
                    model_name,
                    request_started_at,
                    response_finished_at,
                    latency_ms,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    cost_input_usd,
                    cost_output_usd,
                    cost_total_usd,
                    raw_response_id,
                    metadata_json
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    run_id,
                    config.PROJECT_SLUG,
                    provider,
                    model_name,
                    datetime.fromtimestamp(started_at, tz=timezone.utc),
                    datetime.fromtimestamp(finished_at, tz=timezone.utc),
                    int((finished_at - started_at) * 1000),
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    input_cost,
                    output_cost,
                    total_cost,
                    raw_response_id,
                    _to_json(metadata or {}),
                ),
            )
            cur.execute(
                """
                UPDATE runs
                SET input_tokens = runs.input_tokens + %s,
                    output_tokens = runs.output_tokens + %s,
                    total_tokens = runs.total_tokens + %s,
                    total_cost_usd = runs.total_cost_usd + %s
                WHERE id = %s
                """,
                (prompt_tokens, completion_tokens, total_tokens, total_cost, run_id),
            )
        conn.commit()


def purge_old_events(days: int) -> int:
    """Delete events and llm_calls older than `days`. Returns rows deleted.

    Aggregate run stats (runs.total_tokens, runs.total_cost_usd, ...) are not
    affected — only the detailed event/llm_call rows are trimmed.
    """
    if not is_enabled():
        return 0
    cutoff = _utcnow() - timedelta(days=days)
    deleted = 0
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM events WHERE created_at < %s", (cutoff,))
            deleted += cur.rowcount
            cur.execute("DELETE FROM llm_calls WHERE request_started_at < %s", (cutoff,))
            deleted += cur.rowcount
        conn.commit()
    return deleted


def _connect():
    from app.db import get_pool

    return get_pool().connection()


def _dict_row():
    from psycopg.rows import dict_row

    return dict_row


def _to_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True, default=str)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _cost_for_tokens(tokens: int, rate_per_million: Decimal) -> Decimal:
    if not tokens or not rate_per_million:
        return Decimal("0")
    amount = (Decimal(tokens) / Decimal(1_000_000)) * rate_per_million
    return amount.quantize(Decimal("0.000001"))
