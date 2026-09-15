from __future__ import annotations

from psycopg_pool import ConnectionPool

from app import config

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        if not config.DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set")
        _pool = ConnectionPool(config.DATABASE_URL, open=True)
    return _pool
