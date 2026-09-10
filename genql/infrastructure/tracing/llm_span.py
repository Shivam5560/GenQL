"""One span per LLM call, in OpenInference's vocabulary.

Phoenix (and any other OpenInference reader) recognises a span as a model call
by its attributes, not its name: `openinference.span.kind=LLM` plus
`llm.model_name` and the `llm.token_count.*` triple. Set those and a turn's
trace answers "how many calls, how many tokens" without anything in this
codebase counting either.

`llm_span` is a module-level object rather than a function so that the tracer
provider can be swapped — a test installs its own and asserts on real spans,
and a process with tracing switched off installs none. With none installed
nothing is recorded and nothing raises, which is why no call site branches on
whether tracing is enabled.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from opentelemetry.trace import Status, StatusCode, TracerProvider

_SPAN_KIND = "openinference.span.kind"
_MODEL = "llm.model_name"
_INPUT = "input.value"
_OUTPUT = "output.value"
_TOKENS = {
    "prompt_tokens": "llm.token_count.prompt",
    "completion_tokens": "llm.token_count.completion",
    "total_tokens": "llm.token_count.total",
}


def usage_attributes(usage: Mapping[str, Any] | None) -> dict[str, int]:
    """OpenRouter's `usage` block, in OpenInference's names.

    A provider that reports nothing yields nothing: an absent token count is
    better than a zero, which would read as a call that cost nothing.
    """
    if not usage:
        return {}
    return {
        attribute: int(usage[field_name])
        for field_name, attribute in _TOKENS.items()
        if isinstance(usage.get(field_name), int | float)
    }


@dataclass
class _Recorded:
    """The handle a call site uses to report what came back."""

    span: Any = None

    def usage(self, usage: Mapping[str, Any] | None) -> None:
        if self.span is not None:
            self.span.set_attributes(usage_attributes(usage))

    def output(self, text: str) -> None:
        if self.span is not None:
            self.span.set_attribute(_OUTPUT, text)


@dataclass
class _LlmSpan:
    """Opens LLM spans, when a provider has been installed."""

    _provider: TracerProvider | None = field(default=None)

    def set_provider(self, provider: TracerProvider | None) -> None:
        self._provider = provider

    @property
    def provider(self) -> TracerProvider | None:
        """What is installed, so a caller can assert on it or shut it down."""
        return self._provider

    @contextmanager
    def __call__(self, model: str, prompt: str) -> Iterator[_Recorded]:
        if self._provider is None:
            yield _Recorded()
            return
        tracer = self._provider.get_tracer("genql.llm")
        with tracer.start_as_current_span("ChatCompletion") as span:
            span.set_attribute(_SPAN_KIND, "LLM")
            span.set_attribute(_MODEL, model)
            span.set_attribute(_INPUT, prompt)
            try:
                yield _Recorded(span=span)
            except Exception as exc:
                span.set_status(Status(StatusCode.ERROR, str(exc)))
                raise
            span.set_status(Status(StatusCode.OK))


llm_span = _LlmSpan()
