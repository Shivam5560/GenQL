"""Chat-completion providers behind the `ChatProvider` port: OpenRouter's raw
JSON-schema completions, and OpenAI called directly through
`langchain_openai` per the project owner's standing instruction to route
direct-OpenAI calls through LangChain's client rather than a hand-rolled
httpx wrapper."""

from __future__ import annotations

from typing import TypeVar

from langchain_openai import ChatOpenAI
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


@CHAT_PROVIDERS.register("openai")
class OpenAIChatProvider:
    """`with_structured_output` does the schema-constrained call and the
    parse in one step, so — unlike `OpenRouterChatProvider` — there is no
    separate `model_validate_json` stage here: langchain_openai already
    hands back an instance of `response_schema` or raises."""

    def __init__(self, api_key: str, model: str) -> None:
        self._llm = ChatOpenAI(api_key=api_key, model=model)

    def complete(self, prompt: str, response_schema: type[T]) -> T:
        try:
            result = self._llm.with_structured_output(response_schema).invoke(prompt)
        except Exception as exc:  # noqa: BLE001 - langchain_openai raises a wide,
            # unstable mix of openai-sdk and langchain-core exception types
            # across providers/versions; ChatProviderError is the one typed
            # failure every caller already knows how to route.
            raise ChatProviderError(f"OpenAI chat completion failed: {exc}") from exc
        if not isinstance(result, response_schema):
            raise ChatProviderError(
                f"OpenAI response did not match {response_schema.__name__}: got {type(result)!r}"
            )
        return result
