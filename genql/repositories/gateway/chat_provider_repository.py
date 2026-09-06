"""OpenRouter chat completions, requesting a JSON-schema response shaped by
the caller's Pydantic model — a malformed reply becomes a ValidationError
here, not a silent mis-parse three layers up."""

from __future__ import annotations

from typing import TypeVar

from pydantic import BaseModel, ValidationError

from genql.domain.errors import ChatProviderError
from genql.infrastructure.gateway.openrouter_client import OpenRouterClient, OpenRouterError
from genql.repositories.gateway.registry import CHAT_PROVIDERS

T = TypeVar("T", bound=BaseModel)


@CHAT_PROVIDERS.register("openrouter")
class OpenRouterChatProvider:
    def __init__(self, client: OpenRouterClient, model: str) -> None:
        self._client = client
        self._model = model

    def complete(self, prompt: str, response_schema: type[T]) -> T:
        payload = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": response_schema.__name__,
                    "schema": response_schema.model_json_schema(),
                },
            },
        }
        try:
            body = self._client.post_json("/chat/completions", payload)
            content = body["choices"][0]["message"]["content"]
        except (OpenRouterError, KeyError, IndexError) as exc:
            raise ChatProviderError(f"OpenRouter chat completion failed: {exc}") from exc
        try:
            return response_schema.model_validate_json(content)
        except ValidationError as exc:
            raise ChatProviderError(
                f"OpenRouter response did not match {response_schema.__name__}: {exc}"
            ) from exc
