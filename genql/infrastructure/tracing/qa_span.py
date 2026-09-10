"""The root span for one answered question: `QA`.

Everything a turn does — every graph node, every model call, on this thread or
on a strategy's worker thread — belongs under one span, and this is it. The
name is deliberately short and constant: a trace list is read by scanning it,
and "QA" plus the question as `input.value` says more than a name templated
out of the question ever would.

It shares `llm_span`'s tracer provider rather than owning one, so tracing is
armed or disarmed in a single place and a process with tracing off pays for
nothing here either.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from opentelemetry.trace import Status, StatusCode

from genql.infrastructure.tracing.llm_span import llm_span

_SPAN_NAME = "QA"
_SPAN_KIND = "openinference.span.kind"
_INPUT = "input.value"
_DATASOURCE = "genql.datasource"
_THREAD = "genql.thread_id"


@contextmanager
def qa_span(question: str, datasource_name: str | None, thread_id: str) -> Iterator[None]:
    """Opens the turn's root span, or nothing when tracing is off.

    `datasource_name` is optional because a resumed turn answers a
    clarification and names no datasource — the thread it belongs to already
    did, on the turn that opened it.
    """
    provider = llm_span.provider
    if provider is None:
        yield
        return
    tracer = provider.get_tracer("genql.qa")
    with tracer.start_as_current_span(_SPAN_NAME) as span:
        span.set_attribute(_SPAN_KIND, "CHAIN")
        span.set_attribute(_INPUT, question)
        span.set_attribute(_THREAD, thread_id)
        if datasource_name is not None:
            span.set_attribute(_DATASOURCE, datasource_name)
        try:
            yield
        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            raise
        span.set_status(Status(StatusCode.OK))
