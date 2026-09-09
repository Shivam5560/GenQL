"""GET /v1/queries/stream against a fake graph whose `stream` yields a fixed
sequence of `{node: delta}` chunks, asserting the SSE contract: one `stage`
event per chunk in order, exactly one terminal event and it is last, and a
mid-stream failure produces the preceding stage events plus a terminal
`error` event with no `result` event."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from genql.api.app import create_app
from genql.domain.errors import SchemaLinkingError
from tests.integration.api_fakes import FakeContainer, FakeGraph


def _parse_events(body: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    event_name = None
    for line in body.splitlines():
        if line.startswith("event:"):
            event_name = line.removeprefix("event:").strip()
        elif line.startswith("data:") and event_name is not None:
            events.append({"event": event_name, "data": json.loads(line.removeprefix("data:"))})
            event_name = None
    return events


def _client(chunks: list[dict[str, object]]) -> TestClient:
    return TestClient(create_app(FakeContainer(FakeGraph(chunks=chunks))))


def test_one_stage_event_is_emitted_per_chunk_in_order() -> None:
    chunks: list[dict[str, object]] = [
        {"schema_linking": {"links": ()}},
        {"planning": {"plan": None}},
        {"guarded_execution": {"validated_sql": "SELECT 1", "result": None}},
    ]

    response = _client(chunks).get(
        "/v1/queries/stream", params={"question": "q", "datasource": "local"}
    )

    events = _parse_events(response.text)
    stage_events = [e for e in events if e["event"] == "stage"]
    assert [e["data"]["stage"] for e in stage_events] == [
        "schema_linking",
        "planning",
        "guarded_execution",
    ]


def test_exactly_one_terminal_event_and_it_is_last() -> None:
    chunks: list[dict[str, object]] = [
        {"guarded_execution": {"validated_sql": "SELECT 1", "result": None}},
    ]

    response = _client(chunks).get(
        "/v1/queries/stream", params={"question": "q", "datasource": "local"}
    )

    events = _parse_events(response.text)
    terminal = [e for e in events if e["event"] in ("result", "clarification", "error")]
    assert len(terminal) == 1
    assert events[-1] is terminal[0]


class _Interrupt:
    value = "which quarter did you mean?"


def test_an_interrupt_produces_a_paused_stage_then_a_terminal_clarification() -> None:
    chunks: list[dict[str, object]] = [{"__interrupt__": (_Interrupt(),)}]

    response = _client(chunks).get(
        "/v1/queries/stream", params={"question": "q", "datasource": "local"}
    )

    events = _parse_events(response.text)
    assert events[0]["event"] == "stage"
    assert events[0]["data"]["status"] == "paused"
    assert events[-1]["event"] == "clarification"


def test_a_mid_stream_failure_produces_its_preceding_events_then_a_terminal_error() -> None:
    chunks: list[dict[str, object]] = [
        {"schema_linking": {"links": ()}},
        {"planning": SchemaLinkingError("no catalogued object matched")},
    ]

    response = _client(chunks).get(
        "/v1/queries/stream", params={"question": "q", "datasource": "local"}
    )

    events = _parse_events(response.text)
    assert [e["event"] for e in events] == ["stage", "error"]
    assert events[0]["data"]["stage"] == "schema_linking"
    assert events[-1]["data"]["error"] == "SchemaLinkingError"
    assert not any(e["event"] == "result" for e in events)
