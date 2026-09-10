"""AmbiguityGateNode's contested_min_resolved threshold, split out of
test_query_turn_nodes.py to stay under the house file-length limit: at the
production threshold (2), a single resolved dimension no longer makes a turn
contested, but two do — counting only the dimensions the USER had to answer,
never the ones a rule default pre-answered."""

from __future__ import annotations

from genql.api.query_state import initial_state
from genql.api.query_turn_nodes import AmbiguityGateNode
from genql.domain.entities.ambiguity_assessment import AmbiguityAssessment
from tests.unit.test_query_turn_nodes import CLEAR, FakeGate


def test_a_single_resolved_dimension_is_not_contested_at_the_production_threshold() -> None:
    """At contested_min_resolved=2 (Settings' production default), one
    clarifying answer alone — the common case, e.g. a single time_range
    question — no longer pays for multi-candidate generation, critique, and
    probing. Live testing showed 1-resolution contested had become the
    common case, not the exception Phase 6.5 intended it to be."""
    plain_clear = AmbiguityAssessment(is_ambiguous=False)
    state = initial_state("q", "local", "t-1")
    state["clarifications"] = (("time_range", "all time"),)

    update = AmbiguityGateNode(FakeGate(plain_clear), contested_min_resolved=2)(state)

    assert update["contested"] is False


def test_two_resolved_dimensions_are_still_contested_at_the_production_threshold() -> None:
    plain_clear = AmbiguityAssessment(is_ambiguous=False)
    state = initial_state("q", "local", "t-1")
    state["clarifications"] = (("time_range", "all time"), ("filter", "all channels"))

    update = AmbiguityGateNode(FakeGate(plain_clear), contested_min_resolved=2)(state)

    assert update["contested"] is True


def test_an_applied_default_does_not_count_toward_the_threshold() -> None:
    """A rule default is a dimension somebody already ANSWERED, once, in
    YAML — the opposite of a signal that this question is unclear. Counting
    it made contested unavoidable: `semantic/local.yaml` alone defaults
    time_range and comparison_baseline, so every turn against `local`
    started at 2 resolved dimensions and paid for multi-candidate
    generation, critique, and probing before the user typed anything."""
    two_defaults = AmbiguityAssessment(
        is_ambiguous=False,
        applied_defaults=(("time_range", "default_period"), ("filter", "active_only")),
    )
    state = initial_state("q", "local", "t-1")

    update = AmbiguityGateNode(FakeGate(two_defaults), contested_min_resolved=2)(state)

    assert update["contested"] is False


def test_answers_still_count_when_defaults_are_also_applied() -> None:
    """Only the user's answers are counted, but they are still counted in
    full when a default happens to have been applied alongside them."""
    state = initial_state("q", "local", "t-1")
    state["clarifications"] = (("time_range", "all time"), ("filter", "all channels"))

    update = AmbiguityGateNode(FakeGate(CLEAR), contested_min_resolved=2)(state)

    assert update["contested"] is True
