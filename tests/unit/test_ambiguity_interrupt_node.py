"""AmbiguityInterruptNode, split out of test_query_turn_nodes.py to stay under
the house file-length limit: it is tested through a fake `interrupt` rather
than a real one, since calling langgraph's interrupt() outside a running graph
raises. What matters here is the node's bookkeeping — that it appends exactly
the dimension it asked about, paired with exactly the answer it got back — not
the pause itself, which the graph tests exercise for real."""

from __future__ import annotations

import pytest

import genql.api.query_turn_nodes as turn_nodes
from genql.api.query_state import initial_state
from genql.api.query_turn_nodes import AmbiguityInterruptNode
from genql.domain.entities.ambiguity_assessment import AmbiguityAssessment
from genql.domain.errors import AmbiguityGateError
from tests.unit.test_query_turn_nodes import CLEAR, VAGUE


@pytest.fixture()
def no_interrupt(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replaces langgraph's interrupt() with a recorder that returns an answer."""
    asked: list[str] = []

    def fake_interrupt(value: str) -> str:
        asked.append(value)
        return "last quarter"

    monkeypatch.setattr(turn_nodes, "interrupt", fake_interrupt)
    return asked


def test_an_ambiguous_gate_interrupts_with_the_clarifying_question(
    no_interrupt: list[str],
) -> None:
    state = initial_state("q", "local", "t-1")
    state["ambiguity"] = VAGUE

    AmbiguityInterruptNode()(state)

    assert no_interrupt == ["Over what time period?"]


def test_the_answer_is_recorded_against_the_dimension_that_was_asked_about(
    no_interrupt: list[str],
) -> None:
    state = initial_state("q", "local", "t-1")
    state["ambiguity"] = VAGUE

    update = AmbiguityInterruptNode()(state)

    assert update == {"clarifications": (("time_range", "last quarter"),)}


def test_clarifications_accumulate_rather_than_replace(no_interrupt: list[str]) -> None:
    state = initial_state("q", "local", "t-1")
    state["ambiguity"] = VAGUE
    state["clarifications"] = (("entity", "stores"),)

    update = AmbiguityInterruptNode()(state)

    assert update["clarifications"] == (
        ("entity", "stores"),
        ("time_range", "last quarter"),
    )


def test_a_clear_assessment_never_interrupts(no_interrupt: list[str]) -> None:
    state = initial_state("q", "local", "t-1")
    state["ambiguity"] = CLEAR

    update = AmbiguityInterruptNode()(state)

    assert update == {}
    assert no_interrupt == []


def test_no_assessment_yet_never_interrupts(no_interrupt: list[str]) -> None:
    """Defence in depth: unreachable via the real graph (route_after_gate only
    sends this node an ambiguous assessment), but a node that assumed one was
    present would crash rather than no-op on a state it was never meant to
    see."""
    update = AmbiguityInterruptNode()(initial_state("q", "local", "t-1"))

    assert update == {}
    assert no_interrupt == []


def test_an_ambiguous_assessment_with_no_question_raises() -> None:
    """Defence in depth: AmbiguityGateService already rejects this, but a node
    that called interrupt(None) would pause the turn with nothing to show the
    user and no way to answer — raising here fails loud instead."""
    broken = AmbiguityAssessment(is_ambiguous=True, missing_dimension="grain")
    state = initial_state("q", "local", "t-1")
    state["ambiguity"] = broken

    with pytest.raises(AmbiguityGateError):
        AmbiguityInterruptNode()(state)


def test_clarifications_restored_from_a_checkpoint_as_lists_still_work(
    no_interrupt: list[str],
) -> None:
    """A checkpoint round-trip returns `[["entity", "stores"]]`, not
    `(("entity", "stores"),)` — langgraph serialises state through JSON. The
    node normalises, so appending the new answer does not fail on
    `list + tuple`."""
    state = initial_state("q", "local", "t-1")
    state["ambiguity"] = VAGUE
    state["clarifications"] = [["entity", "stores"]]  # type: ignore[typeddict-item]

    update = AmbiguityInterruptNode()(state)

    assert update["clarifications"] == (
        ("entity", "stores"),
        ("time_range", "last quarter"),
    )
