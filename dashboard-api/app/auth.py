from __future__ import annotations

import os

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

DASHBOARD_API_KEY: str = os.getenv("DASHBOARD_API_KEY", "")

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(api_key: str | None = Depends(_api_key_header)) -> None:
    if not api_key or api_key != DASHBOARD_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key",
        )
