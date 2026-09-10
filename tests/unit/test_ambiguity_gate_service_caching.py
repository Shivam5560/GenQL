"""AmbiguityGateService's known_scores caching: a dimension already scored
confidently in a prior round is never re-asked about, and the round that
finally has nothing left to ask pays no model call at all — it is a
deterministic check over cached scores, not a fresh judgement."""

from __future__ import annotations

from tests.unit.test_ambiguity_gate_service import SPECIFIED, FakeChat, service


def test_a_dimension_already_known_and_confident_is_never_rescored() -> None:
    """time_range was scored confidently in a prior round (cached at 0.95);
    only grain is genuinely new. The prompt must ask about grain alone."""
    chat = FakeChat(vague=("grain",), question="At what grain?")
    known = (("time_range", SPECIFIED),)

    assessment = service(chat).assess("q", "local", known_scores=known)

    assert assessment.missing_dimension == "grain"
    prompt = chat.prompts[0]
    assert "time_range" not in prompt
    assert "grain" in prompt


def test_the_round_with_nothing_left_to_ask_makes_no_model_call() -> None:
    """Every open dimension is already cached above threshold — e.g. the
    round right after the user answers the one dimension that was ever
    under-specified. This is the round that used to cost a full re-scoring
    call just to confirm what was already known."""
    known = tuple(
        (d, SPECIFIED) for d in ("entity", "metric", "grain", "filter", "comparison_baseline")
    )
    chat = FakeChat()

    assessment = service(chat).assess(
        "q", "local", answers=(("time_range", "last quarter"),), known_scores=known
    )

    assert assessment.is_ambiguous is False
    assert chat.calls == 0


def test_a_dimension_cached_under_threshold_is_still_asked_about_with_a_fresh_question() -> None:
    """Confidence doesn't need re-measuring, but a clarifying question does —
    the cache only remembers scores, not the question text a prior round
    might not have generated for this exact dimension."""
    known = tuple((d, SPECIFIED) for d in ("entity", "metric", "filter", "comparison_baseline"))
    known = known + (("grain", 0.1),)
    chat = FakeChat(vague=("grain",), question="Which grain?", dimension="grain")

    assessment = service(chat).assess("q", "local", known_scores=known)

    assert assessment.is_ambiguous is True
    assert assessment.missing_dimension == "grain"
    assert assessment.clarifying_question == "Which grain?"
    assert chat.calls == 1


def test_dimension_scores_merges_cached_and_freshly_scored() -> None:
    known = (("time_range", SPECIFIED),)
    chat = FakeChat(vague=("grain",))

    assessment = service(chat).assess("q", "local", known_scores=known)

    scored = dict(assessment.dimension_scores)
    assert scored["time_range"] == SPECIFIED
    assert "grain" in scored
    assert "entity" in scored  # every other open dimension was freshly scored too


def test_no_known_scores_behaves_exactly_as_before() -> None:
    """Backward-compatible: an empty known_scores (every existing caller
    that doesn't pass it) scores every open dimension, same as pre-caching."""
    chat = FakeChat(vague=("grain",), question="At what grain?")

    assessment = service(chat).assess("q", "local")

    assert assessment.missing_dimension == "grain"
    assert chat.calls == 1


def test_ambiguous_assessment_still_carries_its_dimension_scores_for_the_next_round() -> None:
    chat = FakeChat(vague=("time_range",), question="Which quarter?")

    assessment = service(chat).assess("q", "local")

    assert assessment.is_ambiguous is True
    assert dict(assessment.dimension_scores)["time_range"] < 0.7
