"""Thin httpx wrapper for Cohere's own rerank endpoint — the fallback
RerankProviderRegistry keeps registered from day one, not as a future
placeholder, in case OpenRouter ever stops carrying rerank-4-pro."""

from __future__ import annotations

from typing import Any

import httpx

_BASE_URL = "https://api.cohere.com/v1"


class CohereError(Exception):
    """A request to Cohere failed or returned an unexpected shape."""


class CohereClient:
    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        self._client = httpx.Client(
            base_url=_BASE_URL, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout
        )

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(path, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise CohereError(f"Cohere request to {path} failed: {exc}") from exc
        result: dict[str, Any] = response.json()
        return result
