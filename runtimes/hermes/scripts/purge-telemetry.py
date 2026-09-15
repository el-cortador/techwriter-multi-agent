#!/usr/bin/env python3
"""Delete telemetry events/llm_calls older than a retention window.

Usage:
    python runtimes/hermes/scripts/purge-telemetry.py [days]

`days` defaults to the TELEMETRY_RETENTION_DAYS env var, or 90 if that is
also unset. Requires DATABASE_URL (loaded from .env like the rest of the
app). Safe to run repeatedly (e.g. from cron or `docker compose run`).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

CONTAINER_APP_ROOT = Path("/app")
if (CONTAINER_APP_ROOT / "app").exists():
    sys.path.insert(0, str(CONTAINER_APP_ROOT))
else:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hermes"))

from app import telemetry  # noqa: E402


def main() -> None:
    if len(sys.argv) > 1:
        days = int(sys.argv[1])
    else:
        days = int(os.getenv("TELEMETRY_RETENTION_DAYS", "90"))

    if not telemetry.is_enabled():
        print("Telemetry disabled (DATABASE_URL not set) — nothing to purge.")
        return

    deleted = telemetry.purge_old_events(days)
    print(f"Purged {deleted} row(s) older than {days} day(s).")


if __name__ == "__main__":
    main()
