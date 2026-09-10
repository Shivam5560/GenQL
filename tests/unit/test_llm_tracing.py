"""Every LLM call leaves a span carrying its model and its token counts.

The question these exist to answer is "how many calls did that turn make, and
what did they cost" — which nothing in the system could answer before, because
OpenRouter's `usage` block was read off the wire and dropped. The attribute
names are OpenInference's, so Phoenix reads them as an LLM span rather than as
an anonymous one.
"""

from __future__ import annotations

from typing import Any

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from pydantic import BaseModel

from genql.domain.errors import ChatProviderError
from genql.infrastructure.gateway.openrouter_client import OpenRouterError
from genql.infrastructure.tracing.llm_span import llm_span
from genql.repositories.gateway.chat_provider_repository import OpenRouterChatProvider


class Answer(BaseModel):
    intent: str


class FakeClient:
    """Stands in for OpenRouterClient: same one method, canned body."""

    def __init__(self, body: dict[str, Any] | Exception) -> None:
        self.body = body

    def post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if isinstance(self.body, Exception):
            raise self.body
        return self.body


def _body(usage: dict[str, int] | None = None) -> dict[str, Any]:
    body: dict[str, Any] = {"choices": [{"message": {"content": '{"intent": "analytical_sql"}'}}]}
    if usage is not None:
        body["usage"] = usage
    return body


@pytest.fixture()
def spans() -> InMemorySpanExporter:
    """A tracer provider this test owns, so assertions see only its spans."""
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    llm_span.set_provider(provider)
    yield exporter
    llm_span.set_provider(None)


USAGE = {"prompt_tokens": 1180, "completion_tokens": 42, "total_tokens": 1222}


def test_a_completion_records_one_span(spans: InMemorySpanExporter) -> None:
    provider = OpenRouterChatProvider(client=FakeClient(_body(USAGE)), model="anthropic/opus")

    provider.complete("classify this", Answer)

    assert len(spans.get_finished_spans()) == 1


def test_the_span_carries_the_model_and_the_token_counts(spans: InMemorySpanExporter) -> None:
    provider = OpenRouterChatProvider(client=FakeClient(_body(USAGE)), model="anthropic/opus")

    provider.complete("classify this", Answer)

    attributes = spans.get_finished_spans()[0].attributes or {}
    assert attributes["llm.model_name"] == "anthropic/opus"
    assert attributes["llm.token_count.prompt"] == 1180
    assert attributes["llm.token_count.completion"] == 42
    assert attributes["llm.token_count.total"] == 1222
    assert attributes["openinference.span.kind"] == "LLM"


def test_a_provider_that_reports_no_usage_still_records_a_span(
    spans: InMemorySpanExporter,
) -> None:
    provider = OpenRouterChatProvider(client=FakeClient(_body()), model="anthropic/opus")

    provider.complete("classify this", Answer)

    attributes = spans.get_finished_spans()[0].attributes or {}
    assert "llm.token_count.total" not in attributes


def test_a_failed_call_records_a_span_marked_as_an_error(spans: InMemorySpanExporter) -> None:
    provider = OpenRouterChatProvider(
        client=FakeClient(OpenRouterError("502 from upstream")), model="anthropic/opus"
    )

    with pytest.raises(ChatProviderError):
        provider.complete("classify this", Answer)

    span = spans.get_finished_spans()[0]
    assert span.status.is_ok is False


def test_calls_are_counted_one_span_each(spans: InMemorySpanExporter) -> None:
    """The whole point: a turn that made six calls says six, not one."""
    provider = OpenRouterChatProvider(client=FakeClient(_body(USAGE)), model="anthropic/opus")

    for _ in range(6):
        provider.complete("classify this", Answer)

    assert len(spans.get_finished_spans()) == 6
    assert sum(s.attributes["llm.token_count.total"] for s in spans.get_finished_spans()) == 7332


def test_tracing_off_is_not_an_error() -> None:
    """No configured provider means no spans and no exceptions."""
    provider = OpenRouterChatProvider(client=FakeClient(_body(USAGE)), model="anthropic/opus")

    assert provider.complete("classify this", Answer).intent == "analytical_sql"
