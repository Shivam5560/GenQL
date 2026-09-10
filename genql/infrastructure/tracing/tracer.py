"""Points this process's spans at a collector, or at nothing.

Phoenix rather than LangSmith, and the reason is where the data goes: Phoenix
is a container this stack already knows how to run, keeps its traces in the
same Postgres everything else uses, and speaks plain OTLP, so nothing here is
coupled to it. LangSmith would put every prompt and every warehouse column
name on a third party's servers, behind an API key, with self-hosting reserved
for its enterprise tier.

Two paths are instrumented, because there are two ways this codebase reaches a
model. `OpenRouterChatProvider` posts JSON itself and is traced by hand
through `llm_span`. `OpenAIChatProvider` goes through langchain_openai, and
LangGraph runs the pipeline, so OpenInference's LangChain instrumentor covers
both the calls and the node structure around them — which is what makes a
trace read as "this turn, these nodes, these calls" rather than a flat list.
"""

from __future__ import annotations

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import set_tracer_provider

from genql.infrastructure.tracing.llm_span import llm_span

DEFAULT_ENDPOINT = "http://localhost:6006/v1/traces"


def configure_tracing(
    enabled: bool,
    endpoint: str = DEFAULT_ENDPOINT,
    project: str = "genql",
    instrument_langchain: bool = True,
) -> TracerProvider | None:
    """Installs a tracer provider, or returns None when tracing is off.

    Returning the provider rather than keeping it in a module global is what
    lets the caller shut it down — a process that exits without flushing the
    batch processor loses the last few seconds of a trace, which is exactly
    the part someone debugging a slow turn came to look at.
    """
    if not enabled:
        return None
    provider = TracerProvider(
        resource=Resource.create({"service.name": project, "openinference.project.name": project})
    )
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint)))
    llm_span.set_provider(provider)
    # Global too: the LangChain instrumentor and anything else OTel-aware
    # resolve their tracer from here rather than from an argument.
    set_tracer_provider(provider)
    if instrument_langchain:
        _instrument_langchain(provider)
    return provider


def _instrument_langchain(provider: TracerProvider) -> None:
    """Best effort: a missing instrumentor must not stop the server booting."""
    try:
        # Imported here, not at module scope: the instrumentor is an optional
        # extra, and a deployment without it must still be able to boot with
        # tracing on and simply trace less.
        from openinference.instrumentation.langchain import (  # noqa: PLC0415
            LangChainInstrumentor,
        )
    except ImportError:  # pragma: no cover - exercised by deployments without the extra
        return
    LangChainInstrumentor().instrument(tracer_provider=provider, skip_dep_check=True)
