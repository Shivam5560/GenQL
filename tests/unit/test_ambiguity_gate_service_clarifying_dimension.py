"""AmbiguityGateService trusting `clarifying_dimension` only when it agrees
with priority order, split out of test_ambiguity_gate_service.py to stay
under the house file-length limit: the model states which dimension its
`clarifying_question` is actually about, and the caller must record the
user's answer against that dimension rather than assuming priority order,
or an answer lands on the wrong dimension and a dimension nobody asked about
gets silently closed."""

from __future__ import annotations

from tests.unit.test_ambiguity_gate_service import FakeChat, service


def test_the_question_and_the_recorded_dimension_agree() -> None:
    """The bug this guards: the caller files the user's answer under
    `missing_dimension` and closes that dimension for good. If the model wrote
    the question about `filter` while priority order recorded `time_range`,
    the answer lands on the wrong dimension and a dimension nobody asked about
    is silently marked answered."""
    chat = FakeChat(
        vague=("time_range", "filter"),
        question="Which sales channels should be included?",
        dimension="filter",
    )

    assessment = service(chat).assess("total items sold", "local")

    assert assessment.missing_dimension == "filter"
    assert assessment.clarifying_question == "Which sales channels should be included?"


def test_a_named_dimension_that_is_not_under_threshold_is_not_trusted() -> None:
    """A model naming a dimension it scored as specified falls back to
    priority order, so the loop still shrinks by exactly one each round."""
    chat = FakeChat(vague=("grain",), question="Which grain?", dimension="entity")

    assessment = service(chat).assess("q", "local")

    assert assessment.missing_dimension == "grain"


def test_a_named_dimension_outside_the_open_set_is_not_trusted() -> None:
    chat = FakeChat(vague=("grain",), question="Which grain?", dimension="not_a_dimension")

    assessment = service(chat).assess("q", "local")

    assert assessment.missing_dimension == "grain"
