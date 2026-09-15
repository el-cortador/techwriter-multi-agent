from __future__ import annotations

import pytest
from fastapi import HTTPException

from app import auth


def test_require_api_key_accepts_matching_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "DASHBOARD_API_KEY", "secret-key")

    assert auth.require_api_key(api_key="secret-key") is None


def test_require_api_key_rejects_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "DASHBOARD_API_KEY", "secret-key")

    with pytest.raises(HTTPException) as excinfo:
        auth.require_api_key(api_key=None)

    assert excinfo.value.status_code == 401


def test_require_api_key_rejects_wrong_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "DASHBOARD_API_KEY", "secret-key")

    with pytest.raises(HTTPException) as excinfo:
        auth.require_api_key(api_key="wrong-key")

    assert excinfo.value.status_code == 401
