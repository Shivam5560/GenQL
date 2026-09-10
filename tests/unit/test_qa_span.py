"""One question, one trace, rooted at a span called QA.

Without a root of its own, a turn's spans arrive parented on whatever
LangGraph happened to open, and a turn that interrupted before any model call
arrives as nothing at all. `qa_span` gives every turn exactly one parent, so
"how many calls did this question take" is a question the trace can answer.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from genql.infrastructure.tracing.llm_span import llm_span
from genql.infrastructure.tracing.qa_span import qa_span


@pytest.fixture()
def spans() -> Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    llm_span.set_provider(provider)
    yield exporter
    llm_span.set_provider(None)


def test_the_parent_span_is_called_qa(spans: InMemorySpanExporter) -> None:
    with qa_span("how many orders last month", "olist", "t-1"):
        pass

    assert [s.name for s in spans.get_finished_spans()] == ["QA"]


def test_every_model_call_in_the_turn_hangs_off_that_one_parent(
    spans: InMemorySpanExporter,
) -> None:
    with qa_span("how many orders last month", "olist", "t-1"):
        for _ in range(3):
            with llm_span("anthropic/opus", "prompt") as recorded:
                recorded.usage({"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12})

    finished = spans.get_finished_spans()
    parent = next(s for s in finished if s.name == "QA")
    children = [s for s in finished if s.name == "ChatCompletion"]

    assert len(children) == 3
    assert {s.parent.span_id for s in children} == {parent.context.span_id}
    assert {s.context.trace_id for s in children} == {parent.context.trace_id}


def test_the_parent_carries_the_question_it_answered(spans: InMemorySpanExporter) -> None:
    with qa_span("how many orders last month", "olist", "t-1"):
        pass

    attributes = spans.get_finished_spans()[0].attributes or {}
    assert attributes["input.value"] == "how many orders last month"
    assert attributes["genql.datasource"] == "olist"
    assert attributes["genql.thread_id"] == "t-1"
    assert attributes["openinference.span.kind"] == "CHAIN"


def test_a_failed_turn_still_closes_its_parent_span(spans: InMemorySpanExporter) -> None:
    with pytest.raises(RuntimeError), qa_span("q", "olist", "t-1"):
        raise RuntimeError("planner exploded")

    span = spans.get_finished_spans()[0]
    assert span.name == "QA"
    assert span.status.is_ok is False


def test_two_questions_are_two_traces(spans: InMemorySpanExporter) -> None:
    for _ in range(2):
        with qa_span("q", "olist", "t-1"), llm_span("anthropic/opus", "p"):
            pass

    traces = {s.context.trace_id for s in spans.get_finished_spans()}
    assert len(traces) == 2


def test_a_resumed_turn_continues_the_same_trace(spans: InMemorySpanExporter) -> None:
    """An ambiguity clarification is the same query, not a new one — the
    resume must join the trace the question opened, not root a new one."""
    with qa_span("how many orders", "olist", "t-1") as trace_parent:
        pass
    with qa_span("last quarter", None, "t-1", parent=trace_parent):
        pass

    finished = spans.get_finished_spans()
    started, resumed = finished[0], finished[1]
    assert started.context.trace_id == resumed.context.trace_id
    assert resumed.parent is not None
    assert resumed.parent.span_id == started.context.span_id


def test_a_fresh_question_after_a_resume_starts_its_own_trace(spans: InMemorySpanExporter) -> None:
    """A resumed clarification shares a trace with its question, but the next,
    unrelated question on that same thread must not inherit it."""
    with qa_span("how many orders", "olist", "t-1") as trace_parent:
        pass
    with qa_span("last quarter", None, "t-1", parent=trace_parent):
        pass
    with qa_span("and total revenue", "olist", "t-1"):
        pass

    traces = [s.context.trace_id for s in spans.get_finished_spans()]
    assert len(set(traces)) == 2
    assert traces[2] not in traces[:2]


def test_tracing_off_costs_nothing() -> None:
    llm_span.set_provider(None)

    with qa_span("q", "olist", "t-1"):
        pass
