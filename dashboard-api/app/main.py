from __future__ import annotations

import os
from decimal import Decimal

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from psycopg import connect
from psycopg.rows import dict_row

from app.auth import DASHBOARD_API_KEY, require_api_key


def _csv_strings(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    values: list[str] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        values.append(item)
    return values


DATABASE_URL = os.getenv("DATABASE_URL", "")
PROJECT_SLUG = os.getenv("PROJECT_SLUG", "techwriter-super-agent")
DASHBOARD_ALLOWED_ORIGINS = _csv_strings(
    "DASHBOARD_ALLOWED_ORIGINS", "http://127.0.0.1:4173"
)
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sessions (
    id BIGSERIAL PRIMARY KEY,
    project_slug TEXT NOT NULL,
    source TEXT NOT NULL,
    external_session_id TEXT NOT NULL,
    guild_id TEXT,
    channel_id TEXT,
    user_id TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (project_slug, source, external_session_id)
);
CREATE TABLE IF NOT EXISTS runs (
    id BIGSERIAL PRIMARY KEY,
    session_id BIGINT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    project_slug TEXT NOT NULL,
    source TEXT NOT NULL,
    route_kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    model_name TEXT,
    provider TEXT,
    temperature DOUBLE PRECISION,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    duration_ms INTEGER,
    input_chars INTEGER NOT NULL DEFAULT 0,
    output_chars INTEGER NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    total_cost_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
    error_code TEXT,
    error_message TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS llm_calls (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    project_slug TEXT NOT NULL,
    provider TEXT,
    model_name TEXT,
    request_started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    response_finished_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    latency_ms INTEGER,
    prompt_tokens INTEGER NOT NULL DEFAULT 0,
    completion_tokens INTEGER NOT NULL DEFAULT 0,
    total_tokens INTEGER NOT NULL DEFAULT 0,
    cost_input_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
    cost_output_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
    cost_total_usd NUMERIC(12, 6) NOT NULL DEFAULT 0,
    raw_response_id TEXT,
    metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE TABLE IF NOT EXISTS attachments (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    content_type TEXT,
    size_bytes BIGINT,
    storage_path TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS events (
    id BIGSERIAL PRIMARY KEY,
    run_id BIGINT REFERENCES runs(id) ON DELETE CASCADE,
    project_slug TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

app = FastAPI(title="Agent Dashboard API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=DASHBOARD_ALLOWED_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])


@app.on_event("startup")
def startup() -> None:
    if not DASHBOARD_API_KEY:
        raise RuntimeError("DASHBOARD_API_KEY is not set")
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
        conn.commit()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@api_router.get("/overview")
def overview() -> dict:
    with _connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) AS total_runs,
                    COUNT(*) FILTER (WHERE status = 'success') AS success_runs,
                    COUNT(*) FILTER (WHERE status = 'error') AS error_runs,
                    COALESCE(AVG(duration_ms), 0) AS avg_duration_ms,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(total_cost_usd), 0) AS total_cost_usd,
                    COALESCE(AVG(total_tokens), 0) AS avg_tokens_per_run
                FROM runs
                WHERE project_slug = %s
                """,
                (PROJECT_SLUG,),
            )
            totals = cur.fetchone()
            cur.execute(
                """
                SELECT route_kind, COUNT(*) AS runs
                FROM runs
                WHERE project_slug = %s
                GROUP BY route_kind
                ORDER BY runs DESC, route_kind ASC
                LIMIT 5
                """,
                (PROJECT_SLUG,),
            )
            top_routes = cur.fetchall()
            cur.execute(
                """
                SELECT model_name, COUNT(*) AS runs, COALESCE(SUM(total_tokens), 0) AS total_tokens
                FROM runs
                WHERE project_slug = %s
                GROUP BY model_name
                ORDER BY runs DESC, model_name ASC
                """,
                (PROJECT_SLUG,),
            )
            model_usage = cur.fetchall()
    return {
        "project_slug": PROJECT_SLUG,
        "totals": _normalize_row(totals),
        "top_routes": [_normalize_row(row) for row in top_routes],
        "model_usage": [_normalize_row(row) for row in model_usage],
    }


@api_router.get("/activity")
def activity() -> dict:
    with _connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    DATE(started_at) AS day,
                    COUNT(*) AS runs,
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(total_cost_usd), 0) AS total_cost_usd
                FROM runs
                WHERE project_slug = %s
                GROUP BY DATE(started_at)
                ORDER BY day DESC
                LIMIT 30
                """,
                (PROJECT_SLUG,),
            )
            rows = cur.fetchall()
    return {"items": [_normalize_row(row) for row in rows]}


@api_router.get("/sessions")
def sessions(limit: int = 50, offset: int = 0) -> dict:
    with _connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    s.id,
                    s.source,
                    s.external_session_id,
                    s.guild_id,
                    s.channel_id,
                    s.user_id,
                    s.started_at,
                    s.last_activity_at,
                    COUNT(r.id) AS runs,
                    COALESCE(SUM(r.total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(r.total_cost_usd), 0) AS total_cost_usd
                FROM sessions s
                LEFT JOIN runs r ON r.session_id = s.id
                WHERE s.project_slug = %s
                GROUP BY s.id
                ORDER BY s.last_activity_at DESC
                LIMIT %s OFFSET %s
                """,
                (PROJECT_SLUG, limit, offset),
            )
            rows = cur.fetchall()
    return {"items": [_normalize_row(row) for row in rows]}


@api_router.get("/runs")
def runs(limit: int = 100, offset: int = 0) -> dict:
    with _connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    r.id,
                    r.session_id,
                    r.route_kind,
                    r.status,
                    r.model_name,
                    r.provider,
                    r.started_at,
                    r.finished_at,
                    r.duration_ms,
                    r.input_chars,
                    r.output_chars,
                    r.input_tokens,
                    r.output_tokens,
                    r.total_tokens,
                    r.total_cost_usd,
                    r.error_message,
                    s.user_id,
                    s.channel_id
                FROM runs r
                JOIN sessions s ON s.id = r.session_id
                WHERE r.project_slug = %s
                ORDER BY r.started_at DESC
                LIMIT %s OFFSET %s
                """,
                (PROJECT_SLUG, limit, offset),
            )
            rows = cur.fetchall()
    return {"items": [_normalize_row(row) for row in rows]}


@api_router.get("/errors")
def errors(limit: int = 50) -> dict:
    with _connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT
                    id,
                    session_id,
                    route_kind,
                    model_name,
                    started_at,
                    error_message
                FROM runs
                WHERE project_slug = %s
                  AND status = 'error'
                ORDER BY started_at DESC
                LIMIT %s
                """,
                (PROJECT_SLUG, limit),
            )
            rows = cur.fetchall()
    return {"items": [_normalize_row(row) for row in rows]}


@api_router.get("/run-events/{run_id}")
def run_events(run_id: int) -> dict:
    with _connect() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT event_type, payload_json, created_at
                FROM events
                WHERE project_slug = %s
                  AND run_id = %s
                ORDER BY created_at ASC
                """,
                (PROJECT_SLUG, run_id),
            )
            rows = cur.fetchall()
    return {"items": [_normalize_row(row) for row in rows]}


app.include_router(api_router)


def _connect():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")
    return connect(DATABASE_URL)


def _normalize_row(row: dict) -> dict:
    normalized: dict[str, object] = {}
    for key, value in row.items():
        if isinstance(value, Decimal):
            normalized[key] = float(value)
        else:
            normalized[key] = value
    return normalized
