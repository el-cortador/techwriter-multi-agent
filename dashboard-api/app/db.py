from __future__ import annotations

import os

from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv("DATABASE_URL", "")

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set")
        _pool = ConnectionPool(DATABASE_URL, open=True)
    return _pool
