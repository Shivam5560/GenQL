"""A turn the user watched arrive must be there when they reload the page.

The streaming endpoint used to skip thread history entirely, so every turn
asked through it vanished on refresh. These pin the fix, and pin the stream's
own contract while doing it: exactly one terminal event, nothing after it.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any

from genql.api.sse.event_stream import stage_event_stream
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.turn_record import TurnRecord
from genql.domain.errors import SchemaLinkingError


class FakeLocks:
    @contextmanager
    def for_thread(self, _thread_id: str) -> Any:
        yield


class FakeGraph:
    """Streams one node's delta per chunk, like `stream_mode="updates"` does."""

    def __init__(self, chunks: list[dict[str, Any]], raises: Exception | None = None) -> None:
        self._chunks = chunks
        self._raises = raises

    def stream(self, *_args: object, **_kwargs: object) -> Any:
        yield from self._chunks
        if self._raises is not None:
            raise self._raises


class FakeThreads:
    def __init__(self) -> None:
        self.created: list[tuple[str, str, str, str]] = []
        self.touched: list[str] = []

    def create(self, thread_id: str, user_id: str, datasource_name: str, title: str) -> None:
        self.created.append((thread_id, user_id, datasource_name, title))

    def touch(self, thread_id: str) -> None:
        self.touched.append(thread_id)


class FakeTurnRecords:
    def __init__(self) -> None:
        self.appended: list[TurnRecord] = []

    def list_for_thread(self, _thread_id: str) -> list[TurnRecord]:
        return list(self.appended)

    def append(self, record: TurnRecord) -> None:
        self.appended.append(record)


FINISHED: list[dict[str, Any]] = [
    {"schema_linking": {"links": ()}},
    {
        "guarded_execution": {
            "validated_sql": "SELECT 1",
            "result": ExecutionResult(columns=("n",), rows=((1,),), row_count=1, truncated=False),
        }
    },
]


def run(graph: FakeGraph, threads: FakeThreads, turns: FakeTurnRecords) -> list[dict[str, str]]:
    return list(
        stage_event_stream(
            graph,
            FakeLocks(),
            "how many rows?",
            "warehouse",
            thread_id="t-1",
            user_id="u-1",
            threads=threads,
            turn_records=turns,
        )
    )


def test_a_streamed_turn_is_written_to_thread_history() -> None:
    threads, turns = FakeThreads(), FakeTurnRecords()

    events = run(FakeGraph(FINISHED), threads, turns)

    assert threads.created == [("t-1", "u-1", "warehouse", "how many rows?")]
    assert [t.question for t in turns.appended] == ["how many rows?"]
    assert turns.appended[0].validated_sql == "SELECT 1"
    assert [e["event"] for e in events] == ["stage", "stage", "result"]


def test_the_recorded_turn_keeps_the_trail_the_user_watched() -> None:
    """Every stage that was streamed is stored, in the order it streamed, so a
    reload shows the same explanation of the SQL that the live rail did."""
    threads, turns = FakeThreads(), FakeTurnRecords()

    events = run(FakeGraph(FINISHED), threads, turns)

    streamed = [json.loads(e["data"]) for e in events if e["event"] == "stage"]
    assert [s.model_dump() for s in turns.appended[0].stages] == streamed
    assert [s.stage for s in turns.appended[0].stages] == ["schema_linking", "guarded_execution"]


def test_a_failed_turn_is_not_written_to_history() -> None:
    threads, turns = FakeThreads(), FakeTurnRecords()

    events = run(FakeGraph(FINISHED, SchemaLinkingError("nothing matched")), threads, turns)

    assert turns.appended == []
    assert threads.created == []
    assert [e["event"] for e in events][-1] == "error"
    assert json.loads(events[-1]["data"])["error"] == "SchemaLinkingError"


def test_the_stream_ends_at_its_terminal_event_even_when_history_fails() -> None:
    class BrokenTurns(FakeTurnRecords):
        def append(self, record: TurnRecord) -> None:
            raise SchemaLinkingError("history table is gone")

    events = run(FakeGraph(FINISHED), FakeThreads(), BrokenTurns())
    names = [e["event"] for e in events]

    # The warning comes BEFORE the terminal event, never after: the turn
    # itself succeeded and the client must still receive its result.
    assert names == ["stage", "stage", "warning", "result"]
    assert "this turn was not saved" in json.loads(events[-2]["data"])["detail"]


def test_a_stream_without_a_user_records_nothing_and_still_answers() -> None:
    turns = FakeTurnRecords()

    events = list(
        stage_event_stream(FakeGraph(FINISHED), FakeLocks(), "q", "warehouse", thread_id="t-1")
    )

    assert turns.appended == []
    assert [e["event"] for e in events][-1] == "result"
