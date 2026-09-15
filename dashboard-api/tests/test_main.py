from __future__ import annotations

from app.main import _csv_strings


def test_csv_strings_empty_string_returns_empty_list() -> None:
    assert _csv_strings("MISSING_ENV_VAR", "") == []


def test_csv_strings_single_origin() -> None:
    assert _csv_strings("MISSING_ENV_VAR", "http://127.0.0.1:4173") == [
        "http://127.0.0.1:4173"
    ]


def test_csv_strings_multiple_origins() -> None:
    default = "http://127.0.0.1:4173, http://localhost:4173,http://example.com"
    assert _csv_strings("MISSING_ENV_VAR", default) == [
        "http://127.0.0.1:4173",
        "http://localhost:4173",
        "http://example.com",
    ]
