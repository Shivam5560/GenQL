"""Turning tracing on is opt-in, and turning it off costs nothing.

Tracing is off by default because it ships prompts to a collector, which is a
decision a deployment makes rather than a default it inherits. With it off,
`configure_tracing` installs nothing at all — not a provider, not an
instrumentor — so a process that never asked for it pays no per-call cost.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from genql.infrastructure.tracing.llm_span import llm_span
from genql.infrastructure.tracing.tracer import configure_tracing


@pytest.fixture(autouse=True)
def _uninstall() -> Iterator[None]:
    yield
    llm_span.set_provider(None)


def test_tracing_off_installs_nothing() -> None:
    assert configure_tracing(enabled=False, endpoint="http://phoenix:6006/v1/traces") is None
    assert llm_span.provider is None


def test_tracing_on_arms_the_llm_spans() -> None:
    provider = configure_tracing(
        enabled=True, endpoint="http://phoenix:6006/v1/traces", instrument_langchain=False
    )

    assert provider is not None
    assert llm_span.provider is provider
    provider.shutdown()


def test_the_project_name_travels_as_a_resource_attribute() -> None:
    provider = configure_tracing(
        enabled=True,
        endpoint="http://phoenix:6006/v1/traces",
        project="genql-dev",
        instrument_langchain=False,
    )

    assert provider is not None
    attributes = provider.resource.attributes
    assert attributes["openinference.project.name"] == "genql-dev"
    assert attributes["service.name"] == "genql-dev"
    provider.shutdown()
