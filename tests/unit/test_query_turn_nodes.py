"""The four new adapters, with no provider, no database, and no graph.

AmbiguityGateNode never interrupts — it only assesses and returns, so these
tests need no fake interrupt at all. AmbiguityInterruptNode (the one that
does interrupt, tested through a fake rather than a real one) has its own
tests in test_ambiguity_interrupt_node.py, split out to stay under the house
file-length limit — VAGUE and CLEAR below are shared with that file.
"""

from __future__ import annotations

import pytest

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
        known_scores: tuple[tuple[str, float], ...] = (),
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


def test_intent_classification_writes_the_intent() -> None:
    classifier = FakeClassifier("metadata_question")

    update = IntentClassificationNode(classifier)(initial_state("q", "local", "t-1"))

    assert update == {"intent": "metadata_question"}
    assert classifier.questions == ["q"]


def test_intent_classification_does_not_swallow_its_typed_failure() -> None:
    with pytest.raises(IntentClassificationError):
        IntentClassificationNode(RaisingClassifier())(initial_state("q", "local", "t-1"))


def test_an_unambiguous_gate_writes_the_assessment_and_asks_nothing() -> None:
    update = AmbiguityGateNode(FakeGate(CLEAR))(initial_state("q", "local", "t-1"))

    assert update == {
        "ambiguity": CLEAR,
        "contested": False,
        "gate_scores": (),
        "assumptions": (),
    }


def test_an_ambiguous_gate_never_interrupts_itself() -> None:
    """AmbiguityGateNode always returns normally — it is AmbiguityInterruptNode
    that pauses — so its own result (including gate_scores) is always
    committed to state before any interrupt can happen."""
    update = AmbiguityGateNode(FakeGate(VAGUE))(initial_state("q", "local", "t-1"))

    assert update == {"ambiguity": VAGUE, "gate_scores": (), "assumptions": ()}


def test_the_gate_is_given_the_answers_collected_so_far() -> None:
    gate = FakeGate(VAGUE)
    state = initial_state("q", "local", "t-1")
    state["clarifications"] = (("entity", "stores"),)

    AmbiguityGateNode(gate)(state)

    assert gate.calls == [("q", "local", (("entity", "stores"),))]


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


def test_a_clear_gate_with_no_prior_answers_and_no_defaults_is_not_contested() -> None:
    plain_clear = AmbiguityAssessment(is_ambiguous=False)

    update = AmbiguityGateNode(FakeGate(plain_clear))(initial_state("q", "local", "t-1"))

    assert update == {
        "ambiguity": plain_clear,
        "contested": False,
        "gate_scores": (),
        "assumptions": (),
    }


def test_a_clear_gate_after_a_resumed_answer_is_contested() -> None:
    plain_clear = AmbiguityAssessment(is_ambiguous=False)
    state = initial_state("q", "local", "t-1")
    state["clarifications"] = (("time_range", "last quarter"),)

    update = AmbiguityGateNode(FakeGate(plain_clear))(state)

    assert update["contested"] is True


def test_a_clear_gate_with_only_an_applied_default_is_not_contested() -> None:
    """Even at the permissive threshold of 1, a rule default alone does not
    contest a turn: it is a dimension pre-answered in YAML for every
    question against the datasource, not a gap this question left open."""
    update = AmbiguityGateNode(FakeGate(CLEAR))(initial_state("q", "local", "t-1"))

    assert update["contested"] is False
