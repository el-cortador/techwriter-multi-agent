# techwriter-multi-agent

`techwriter-multi-agent` is a self-hosted Discord documentation assistant with a built-in analytics dashboard.

This alpha release includes:
- a Discord gateway that routes requests to local documentation skills
- OpenRouter-backed text and vision generation
- a Postgres-backed telemetry pipeline
- a browser dashboard for runs, sessions, tokens, errors, and estimated cost

## Alpha Scope

This repository is currently suitable for:
- local use
- an internal team bot
- controlled self-hosted testing

This repository is not yet packaged as a hardened public SaaS or multi-tenant release.

Current alpha limitations:
- no authentication on the dashboard UI/API
- no historical backfill for pre-telemetry sessions
- model pricing is configured manually through env vars
- Postgres schema is created at runtime, without a separate migration workflow
- Discord is the only production-wired input channel in this repository

## Services

`docker compose` starts four services:
- `hermes-discord`: the main Discord gateway and agent runtime
- `postgres`: telemetry storage
- `dashboard-api`: analytics API over telemetry data
- `dashboard-ui`: browser UI for project metrics

## Repository Layout

```text
manifest.yaml          agent contract (skills, secrets, runtime)
core/                  runtime-independent behavior spec
runtimes/hermes/       skill packages, install/verify scripts, ops docs
hermes/                Discord gateway code, tests, Dockerfile
dashboard-api/         analytics API
dashboard-ui/          analytics UI
```

## Quick Start

1. Run the installer (creates `.env` from `.env.example`, never overwrites):

```powershell
runtimes\hermes\install.ps1
```

2. Fill in the required secrets in `.env`:
   - `DISCORD_BOT_TOKEN`
   - `OPENROUTER_API_KEY`
   - `FIGMA_TOKEN` if Figma flows are needed
   - `GITHUB_TOKEN` and `JIRA_*` if release note generation is needed
3. Start the stack:

```powershell
docker compose up -d --build
```

4. Open the dashboard:

```text
http://127.0.0.1:4173
```

## Required Environment

Core runtime:
- `DISCORD_BOT_TOKEN`
- `OPENROUTER_API_KEY`
- `DISCORD_ALLOWED_GUILD_IDS`
- `DISCORD_ALLOWED_CHANNEL_IDS`
- `DISCORD_ALLOWED_USER_IDS`

Project/runtime defaults:
- `PROJECT_SLUG=techwriter-multi-agent`
- `LLM_MODEL_NAME=deepseek/deepseek-v4-pro`
- `HERMES_VISION_MODEL=google/gemini-2.5-flash`

Telemetry and dashboard:
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `DATABASE_URL`
- `DASHBOARD_PORT`
- `DASHBOARD_API_KEY` — required by `dashboard-api`; requests to `/api/*` must send it as
  the `X-API-Key` header (`/health` is exempt)

## Pricing Configuration

The dashboard stores estimated cost from token usage. Pricing is manual and must be updated when model rates change.

Current alpha defaults:
- `LLM_COST_INPUT_PER_1M=0.435`
- `LLM_COST_OUTPUT_PER_1M=0.87`
- `VISION_COST_INPUT_PER_1M=0.30`
- `VISION_COST_OUTPUT_PER_1M=2.50`

These values correspond to:
- `deepseek/deepseek-v4-pro`
- `google/gemini-2.5-flash`

## Dashboard Data Model

Telemetry is stored in Postgres as:
- `sessions`
- `runs`
- `llm_calls`
- `attachments`
- `events`

The dashboard currently exposes:
- overview totals
- daily activity
- recent sessions
- recent runs
- model usage
- recent errors

## Verification

The current alpha was verified with:

```powershell
python -m venv .venv
.venv/Scripts/pip install -r hermes/requirements.txt pytest
.venv/Scripts/python -m pytest hermes/tests -q
.venv/Scripts/python -m compileall hermes dashboard-api -q
docker compose config -q
runtimes\hermes\scripts\verify-install.ps1
docker compose up -d --build
```

Manual end-to-end checklist: `runtimes/hermes/docs/SMOKE_TEST_PLAN.md`.

## Release Recommendation

For GitHub Releases, publish this version as:

```text
v0.2.0-alpha.1
```

Recommended release title:

```text
techwriter-multi-agent v0.2.0-alpha.1
```
