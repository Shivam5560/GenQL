"""The three new adapters, with no provider, no database, and no graph.

AmbiguityGateNode is the one with real behaviour, and it is tested through a
fake `interrupt` rather than a real one: calling langgraph's interrupt() outside
a running graph raises, and what these tests need to assert is the node's
bookkeeping — that it appends exactly the dimension it asked about, paired with
exactly the answer it got back. The real interrupt is exercised by the graph
tests below and by the checkpointer integration test.
"""

from __future__ import annotations

import pytest

import genql.api.query_turn_nodes as turn_nodes
from genql.api.query_state import initial_state
from genql.api.query_turn_nodes import (
    AmbiguityGateNode,
    DomainScopingNode,
    IntentClassificationNode,
)
from genql.domain.entities.ambiguity_assessment import AmbiguityAssessment
from genql.domain.errors import IntentClassificationError

VAGUE = AmbiguityAssessment(
    is_ambiguous=True,
    missing_dimension="time_range",
    clarifying_question="Over what time period?",
    applied_defaults=(("filter", "active_only"),),
)
CLEAR = AmbiguityAssessment(is_ambiguous=False, applied_defaults=(("filter", "active_only"),))


class FakeClassifier:
    def __init__(self, intent: str = "analytical_sql") -> None:
        self.intent = intent
        self.questions: list[str] = []

    def classify(self, question: str) -> str:
        self.questions.append(question)
        return self.intent


class RaisingClassifier:
    def classify(self, question: str) -> str:
        raise IntentClassificationError("bad label")


class FakeGate:
    """Returns each queued assessment in turn, recording what it was asked."""

    def __init__(self, *assessments: AmbiguityAssessment) -> None:
        self.queue = list(assessments)
        self.calls: list[tuple[str, str, tuple[tuple[str, str], ...]]] = []

    def assess(
        self,
        question: str,
        datasource_name: str,
        answers: tuple[tuple[str, str], ...] = (),
        links: tuple[object, ...] = (),
    ) -> AmbiguityAssessment:
        self.calls.append((question, datasource_name, answers))
        return self.queue.pop(0) if self.queue else CLEAR


class FakeScoper:
    def __init__(self, domain_id: int | None) -> None:
        self.domain_id = domain_id
        self.calls: list[tuple[str, str]] = []

    def resolve(self, question: str, datasource_name: str) -> int | None:
        self.calls.append((question, datasource_name))
        return self.domain_id


@pytest.fixture()
def no_interrupt(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replaces langgraph's interrupt() with a recorder that returns an answer."""
    asked: list[str] = []

    def fake_interrupt(value: str) -> str:
        asked.append(value)
        return "last quarter"

    monkeypatch.setattr(turn_nodes, "interrupt", fake_interrupt)
    return asked


def test_intent_classification_writes_the_intent() -> None:
    classifier = FakeClassifier("metadata_question")

    update = IntentClassificationNode(classifier)(initial_state("q", "local", "t-1"))

    assert update == {"intent": "metadata_question"}
    assert classifier.questions == ["q"]


def test_intent_classification_does_not_swallow_its_typed_failure() -> None:
    with pytest.raises(IntentClassificationError):
        IntentClassificationNode(RaisingClassifier())(initial_state("q", "local", "t-1"))


def test_an_unambiguous_gate_writes_the_assessment_and_asks_nothing(
    no_interrupt: list[str],
) -> None:
    update = AmbiguityGateNode(FakeGate(CLEAR))(initial_state("q", "local", "t-1"))

    assert update == {"ambiguity": CLEAR, "contested": True}
    assert no_interrupt == []


def test_an_ambiguous_gate_interrupts_with_the_clarifying_question(
    no_interrupt: list[str],
) -> None:
    AmbiguityGateNode(FakeGate(VAGUE))(initial_state("q", "local", "t-1"))

    assert no_interrupt == ["Over what time period?"]


def test_the_answer_is_recorded_against_the_dimension_that_was_asked_about(
    no_interrupt: list[str],
) -> None:
    update = AmbiguityGateNode(FakeGate(VAGUE))(initial_state("q", "local", "t-1"))

    assert update["clarifications"] == (("time_range", "last quarter"),)
    assert update["ambiguity"] == VAGUE


def test_clarifications_accumulate_rather_than_replace(no_interrupt: list[str]) -> None:
    state = initial_state("q", "local", "t-1")
    state["clarifications"] = (("entity", "stores"),)

    update = AmbiguityGateNode(FakeGate(VAGUE))(state)

    assert update["clarifications"] == (
        ("entity", "stores"),
        ("time_range", "last quarter"),
    )


def test_the_gate_is_given_the_answers_collected_so_far(no_interrupt: list[str]) -> None:
    gate = FakeGate(VAGUE)
    state = initial_state("q", "local", "t-1")
    state["clarifications"] = (("entity", "stores"),)

    AmbiguityGateNode(gate)(state)

    assert gate.calls == [("q", "local", (("entity", "stores"),))]


def test_an_ambiguous_assessment_with_no_question_never_interrupts(
    no_interrupt: list[str],
) -> None:
    """Defence in depth: AmbiguityGateService already rejects this, but a node
    that called interrupt(None) would pause the turn with nothing to show the
    user and no way to answer."""
    broken = AmbiguityAssessment(is_ambiguous=True, missing_dimension="grain")

    update = AmbiguityGateNode(FakeGate(broken))(initial_state("q", "local", "t-1"))

    assert no_interrupt == []
    assert update == {"ambiguity": broken}


def test_clarifications_restored_from_a_checkpoint_as_lists_still_work(
    no_interrupt: list[str],
) -> None:
    """A checkpoint round-trip returns `[["entity", "stores"]]`, not
    `(("entity", "stores"),)` — langgraph serialises state through JSON. The
    node normalises, so the gate still receives the tuples its port declares
    and appending the new answer does not fail on `list + tuple`."""
    gate = FakeGate(VAGUE)
    state = initial_state("q", "local", "t-1")
    state["clarifications"] = [["entity", "stores"]]  # type: ignore[typeddict-item]

    update = AmbiguityGateNode(gate)(state)

    assert gate.calls == [("q", "local", (("entity", "stores"),))]
    assert update["clarifications"] == (
        ("entity", "stores"),
        ("time_range", "last quarter"),
    )


def test_domain_scoping_writes_the_resolved_id() -> None:
    scoper = FakeScoper(7)

    update = DomainScopingNode(scoper)(initial_state("q", "local", "t-1"))

    assert update == {"domain_id": 7}
    assert scoper.calls == [("q", "local")]


def test_domain_scoping_writes_none_when_nothing_resolves() -> None:
    update = DomainScopingNode(FakeScoper(None))(initial_state("q", "local", "t-1"))

    assert update == {"domain_id": None}


def test_an_explicit_domain_id_is_never_overwritten() -> None:
    """--domain-id is the manual override for a mis-scoped question, per the
    spec's §11 mitigation. A stage that recomputed over it would delete the
    override."""
    scoper = FakeScoper(7)

    update = DomainScopingNode(scoper)(initial_state("q", "local", "t-1", domain_id=42))

    assert update == {}
    assert scoper.calls == []


def test_a_clear_gate_with_no_prior_answers_and_no_defaults_is_not_contested(
    no_interrupt: list[str],
) -> None:
    plain_clear = AmbiguityAssessment(is_ambiguous=False)

    update = AmbiguityGateNode(FakeGate(plain_clear))(initial_state("q", "local", "t-1"))

    assert update == {"ambiguity": plain_clear, "contested": False}


def test_a_clear_gate_after_a_resumed_answer_is_contested(no_interrupt: list[str]) -> None:
    plain_clear = AmbiguityAssessment(is_ambiguous=False)
    state = initial_state("q", "local", "t-1")
    state["clarifications"] = (("time_range", "last quarter"),)

    update = AmbiguityGateNode(FakeGate(plain_clear))(state)

    assert update["contested"] is True


def test_a_clear_gate_with_an_applied_default_is_contested(no_interrupt: list[str]) -> None:
    update = AmbiguityGateNode(FakeGate(CLEAR))(initial_state("q", "local", "t-1"))

    assert update["contested"] is True
