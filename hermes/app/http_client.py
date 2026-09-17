from __future__ import annotations

from typing import Any

import httpx
import requests
from tenacity import retry, retry_if_exception_type, retry_if_result, stop_after_attempt, wait_exponential

RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})

_RETRYABLE_NETWORK_EXCEPTIONS = (
    requests.ConnectionError,
    requests.Timeout,
    httpx.ConnectError,
    httpx.TimeoutException,
)


def _is_retryable_response(response: object) -> bool:
    return getattr(response, "status_code", None) in RETRYABLE_STATUS_CODES


def _retrying(func):
    return retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=(
            retry_if_exception_type(_RETRYABLE_NETWORK_EXCEPTIONS)
            | retry_if_result(_is_retryable_response)
        ),
    )(func)


@_retrying
def get(url: str, **kwargs: Any) -> requests.Response:
    """Retrying wrapper around requests.get: retries 429/5xx/timeout/connection
    errors, not 401/403/404 or other 4xx."""
    return requests.get(url, **kwargs)


@_retrying
def httpx_get(client: httpx.Client, url: str, **kwargs: Any) -> httpx.Response:
    """Same retry policy as `get`, for an existing httpx.Client instance."""
    return client.get(url, **kwargs)
