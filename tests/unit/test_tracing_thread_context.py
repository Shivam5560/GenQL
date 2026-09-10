"""Candidate generation fans out across threads; its spans must not.

CandidateGenerationService runs every strategy in a ThreadPoolExecutor, and a
worker thread starts with an empty OpenTelemetry context — so without help,
each strategy's model call opens a *root* span and one turn arrives at the
collector as several unrelated traces. That is exactly the reading that makes
a seven-call turn look like a one-call turn.
"""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import ClassVar

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from genql.infrastructure.query.candidate_strategy_factory import CandidateStrategyFactoryImpl
from genql.infrastructure.tracing.llm_span import llm_span
from genql.infrastructure.tracing.thread_context import ContextCarryingStrategy


class StubStrategy:
    """Opens an LLM span the way a real strategy's ChatProvider would."""

    variant_count: ClassVar[int] = 1

    def generate_variants(self, plan, links, violations, examples):  # type: ignore[no-untyped-def]
        with llm_span("anthropic/opus", "generate") as recorded:
            recorded.usage({"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12})
        return ()


@pytest.fixture()
def spans() -> Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    llm_span.set_provider(provider)
    yield exporter
    llm_span.set_provider(None)


def _run_in_a_worker(strategy: object) -> None:
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(strategy.generate_variants, None, (), (), ()).result()  # type: ignore[attr-defined]


def test_an_unwrapped_strategy_loses_the_turn_it_belonged_to(
    spans: InMemorySpanExporter,
) -> None:
    tracer = llm_span.provider.get_tracer("test")  # type: ignore[union-attr]

    with tracer.start_as_current_span("turn") as turn:
        _run_in_a_worker(StubStrategy())
        turn_trace_id = turn.get_span_context().trace_id

    llm = next(s for s in spans.get_finished_spans() if s.name == "ChatCompletion")
    assert llm.context.trace_id != turn_trace_id


def test_a_carried_strategy_stays_inside_the_turns_trace(spans: InMemorySpanExporter) -> None:
    tracer = llm_span.provider.get_tracer("test")  # type: ignore[union-attr]

    with tracer.start_as_current_span("turn") as turn:
        # Wrapped where the strategies are built — on the calling thread,
        # which is the only place the turn's context can still be seen.
        carried = ContextCarryingStrategy(StubStrategy())
        _run_in_a_worker(carried)
        turn_trace_id = turn.get_span_context().trace_id

    llm = next(s for s in spans.get_finished_spans() if s.name == "ChatCompletion")
    assert llm.context.trace_id == turn_trace_id


def test_the_wrapper_keeps_the_strategys_variant_count() -> None:
    assert ContextCarryingStrategy(StubStrategy()).variant_count == 1


def test_the_factory_hands_out_carried_strategies() -> None:
    strategies = CandidateStrategyFactoryImpl().all(chat=object())

    assert strategies
    assert all(isinstance(s, ContextCarryingStrategy) for s in strategies)
