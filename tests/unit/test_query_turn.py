"""Turning what the graph returned into what the CLI prints.

Three shapes come back from an invoke: a mapping carrying `__interrupt__` (the
turn paused), a mapping whose intent short-circuited it (no SQL was ever
attempted), and a finished mapping. The lock is asserted here rather than in the
CLI test because it is the api layer that holds it, and because "released even
when the graph raises" is exactly the behaviour a `finally` gets wrong.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

import pytest

from genql.api.query_state import initial_state
from genql.api.query_turn import new_thread_id, resume_turn, start_turn
from genql.domain.entities.ambiguity_assessment import AmbiguityAssessment
from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.errors import PlanningError, UnknownThreadError

RESULT = ExecutionResult(columns=("n",), rows=((7,),), row_count=1, truncated=False)


class Interrupt:
    def __init__(self, value: str) -> None:
        self.value = value
        self.id = "i-1"


class FakeSnapshot:
    def __init__(self, interrupts: tuple[Any, ...], values: dict[str, Any] | None = None) -> None:
        self.interrupts = interrupts
        self.values = values or {}


class FakeGraph:
    """Records every invoke and returns whatever it was primed with.

    `has_pending_interrupt` backs `get_state`, which `resume_query` checks
    before invoking — defaults to True so every existing resume test, which
    means to exercise a real pause, keeps working unchanged.
    """

    def __init__(self, outcome: Any, has_pending_interrupt: bool = True) -> None:
        self.outcome = outcome
        self.invocations: list[tuple[Any, Any]] = []
        self._has_pending_interrupt = has_pending_interrupt

    def invoke(self, payload: Any, config: Any = None) -> Any:
        self.invocations.append((payload, config))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    def get_state(self, config: Any) -> FakeSnapshot:
        return FakeSnapshot((Interrupt("pending"),) if self._has_pending_interrupt else ())


class FakeLock:
    def __init__(self, log: list[str], thread_id: str) -> None:
        self.log = log
        self.thread_id = thread_id

    def __enter__(self) -> None:
        self.log.append(f"acquire:{self.thread_id}")

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.log.append(f"release:{self.thread_id}")


class FakeLocks:
    def __init__(self) -> None:
        self.log: list[str] = []

    def for_thread(self, thread_id: str) -> FakeLock:
        return FakeLock(self.log, thread_id)


def finished_state() -> dict[str, Any]:
    state: dict[str, Any] = dict(initial_state("q", "local", "t-1"))
    state["intent"] = "analytical_sql"
    state["ambiguity"] = AmbiguityAssessment(
        is_ambiguous=False, applied_defaults=(("time_range", "default_period"),)
    )
    state["validated_sql"] = "SELECT 7 LIMIT 1"
    state["result"] = RESULT
    return state


def paused_state() -> dict[str, Any]:
    state: dict[str, Any] = dict(initial_state("q", "local", "t-1"))
    state["intent"] = "analytical_sql"
    state["ambiguity"] = AmbiguityAssessment(
        is_ambiguous=True,
        missing_dimension="time_range",
        clarifying_question="Over what time period?",
        applied_defaults=(("filter", "active_only"),),
    )
    state["__interrupt__"] = [Interrupt("Over what time period?")]
    return state


def short_circuited_state() -> dict[str, Any]:
    state: dict[str, Any] = dict(initial_state("q", "local", "t-1"))
    state["intent"] = "non_sql"
    return state


def test_a_generated_thread_id_is_unique_and_non_empty() -> None:
    assert new_thread_id() != new_thread_id()
    assert new_thread_id()


def test_a_finished_turn_carries_sql_rows_and_the_applied_defaults() -> None:
    response = start_turn(FakeGraph(finished_state()), FakeLocks(), "q", "local")

    assert response.clarifying_question is None
    assert response.intent is None
    assert response.validated_sql == "SELECT 7 LIMIT 1"
    assert response.result == RESULT
    assert response.applied_defaults == (("time_range", "default_period"),)


def test_a_paused_turn_carries_the_question_and_the_thread_id() -> None:
    graph = FakeGraph(paused_state())

    response = start_turn(graph, FakeLocks(), "q", "local", thread_id="t-9")

    assert response.thread_id == "t-9"
    assert response.clarifying_question == "Over what time period?"
    assert response.validated_sql is None
    assert response.result is None
    assert response.applied_defaults == (("filter", "active_only"),)


def test_a_short_circuited_turn_reports_only_its_intent() -> None:
    response = start_turn(FakeGraph(short_circuited_state()), FakeLocks(), "q", "local")

    assert response.intent == "non_sql"
    assert response.clarifying_question is None
    assert response.validated_sql is None


def test_a_finished_analytical_turn_does_not_report_an_intent() -> None:
    """intent is set only on a short circuit, per the spec's §2 — reporting
    'analytical_sql' beside real rows would be noise on every successful turn."""
    response = start_turn(FakeGraph(finished_state()), FakeLocks(), "q", "local")

    assert response.intent is None


def test_a_generated_thread_id_is_used_when_none_is_given() -> None:
    graph = FakeGraph(paused_state())

    response = start_turn(graph, FakeLocks(), "q", "local")

    assert response.thread_id
    _, config = graph.invocations[0]
    assert config == {"configurable": {"thread_id": response.thread_id}}


def test_the_question_datasource_and_domain_reach_the_graph() -> None:
    graph = FakeGraph(finished_state())

    start_turn(graph, FakeLocks(), "how many stores", "wh2", domain_id=42, thread_id="t-3")

    payload, _ = graph.invocations[0]
    assert payload["question"] == "how many stores"
    assert payload["datasource_name"] == "wh2"
    assert payload["domain_id"] == 42
    assert payload["thread_id"] == "t-3"


def test_resuming_sends_a_command_carrying_the_answer() -> None:
    graph = FakeGraph(finished_state())

    response = resume_turn(graph, FakeLocks(), "last quarter", "t-7")

    payload, config = graph.invocations[0]
    assert payload.resume == "last quarter"
    assert config == {"configurable": {"thread_id": "t-7"}}
    assert response.thread_id == "t-7"


def test_a_resumed_turn_can_pause_again() -> None:
    response = resume_turn(FakeGraph(paused_state()), FakeLocks(), "stores", "t-7")

    assert response.clarifying_question == "Over what time period?"
    assert response.thread_id == "t-7"


def test_the_lock_is_taken_for_the_thread_and_released() -> None:
    locks = FakeLocks()

    start_turn(FakeGraph(finished_state()), locks, "q", "local", thread_id="t-5")

    assert locks.log == ["acquire:t-5", "release:t-5"]


def test_the_lock_is_taken_on_resume_too() -> None:
    locks = FakeLocks()

    resume_turn(FakeGraph(finished_state()), locks, "last quarter", "t-5")

    assert locks.log == ["acquire:t-5", "release:t-5"]


def test_the_lock_is_released_when_the_graph_raises() -> None:
    locks = FakeLocks()

    with pytest.raises(PlanningError):
        start_turn(FakeGraph(PlanningError("no links")), locks, "q", "local", thread_id="t-5")

    assert locks.log == ["acquire:t-5", "release:t-5"]


def test_the_typed_failure_is_not_swallowed() -> None:
    with pytest.raises(PlanningError):
        resume_turn(FakeGraph(PlanningError("no links")), FakeLocks(), "a", "t-5")


def test_resuming_an_unknown_thread_raises_a_typed_error_and_releases_the_lock() -> None:
    """No checkpoint means no pending interrupt: resume_query must refuse
    before invoking the graph, not let it run from START and blow up on a
    missing state key."""
    locks = FakeLocks()
    graph = FakeGraph(finished_state(), has_pending_interrupt=False)

    with pytest.raises(UnknownThreadError):
        resume_turn(graph, locks, "answer", "t-ghost")

    assert graph.invocations == []
    assert locks.log == ["acquire:t-ghost", "release:t-ghost"]
