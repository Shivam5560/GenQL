"""Thin httpx wrapper for OpenRouter's chat, embeddings, and rerank
endpoints. No `openai` SDK: three JSON-over-HTTPS calls do not justify a
dependency that exists only to wrap them. Built here; called only from
`genql/repositories/gateway/`."""

from __future__ import annotations

from typing import Any

import httpx

_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterError(Exception):
    """A request to OpenRouter failed or returned an unexpected shape."""


class OpenRouterClient:
    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        self._client = httpx.Client(
            base_url=_BASE_URL, headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout
        )

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(path, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OpenRouterError(f"OpenRouter request to {path} failed: {exc}") from exc
        result: dict[str, Any] = response.json()
        return result
