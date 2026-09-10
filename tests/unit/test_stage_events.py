"""A stage delta becomes one short line, never the delta itself: a delta can
carry every schema link or every candidate statement, and putting that on the
wire would make the event stream the widest interface in the system.

This file is the dispatcher's contract — which stage, which status, and the
line. What each summariser puts in `facts` is `test_stage_facts.py`.
"""

from __future__ import annotations

from genql.api.sse.stage_events import to_stage_event
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.stage_event import StageEvent

PLAN = QueryPlan(question="q", plan_text="sum sales by month", referenced_objects=("local.a.b",))


def facts(event: StageEvent) -> dict[str, str]:
    return dict(event.facts)


def test_a_completed_node_becomes_a_completed_event_named_for_the_node() -> None:
    event = to_stage_event("planning", {"plan": PLAN})

    assert event.stage == "planning"
    assert event.status == "completed"


def test_a_schema_linking_delta_is_summarized_by_count_not_by_content() -> None:
    links = tuple(SchemaLink(object_qualified_name=f"local.s.o{i}") for i in range(12))

    event = to_stage_event("schema_linking", {"links": links})

    assert event.detail is not None
    assert "12" in event.detail
    assert "o11" not in event.detail


def test_a_node_with_no_summariser_still_produces_an_event() -> None:
    """A stage added by a later phase must stream without editing this file."""
    event = to_stage_event("a_future_stage", {"whatever": 1})

    assert event.stage == "a_future_stage"
    assert event.status == "completed"


def test_a_detail_line_is_never_longer_than_the_cap() -> None:
    event = to_stage_event(
        "planning", {"plan": QueryPlan(question="q", plan_text="x" * 5_000, referenced_objects=())}
    )

    assert event.detail is not None
    assert len(event.detail) <= 200


# ── The pause ───────────────────────────────────────────────────────────────


def test_an_interrupt_becomes_a_paused_event_attributed_to_the_gate() -> None:
    class _Interrupt:
        value = {"question": "which quarter?", "suggested_answer": "Q4", "options": ("Q3", "Q4")}

    event = to_stage_event("__interrupt__", (_Interrupt(),))

    assert event.stage == "ambiguity_gate"
    assert event.status == "paused"
    assert event.detail == "which quarter?"


def test_the_pause_never_puts_a_serialized_mapping_on_the_wire() -> None:
    """The payload interrupt() carries is a mapping. Stringifying it whole put
    a Python dict repr in `detail` — which a reading client then detected and
    threw away, losing the stage's whole explanation rather than showing a
    blob. The suggestion and the options travel as facts instead."""

    class _Interrupt:
        value = {"question": "which quarter?", "suggested_answer": "Q4", "options": ("Q3", "Q4")}

    event = to_stage_event("__interrupt__", (_Interrupt(),))

    assert event.detail is not None
    assert "'question':" not in event.detail
    assert "{" not in event.detail
    assert facts(event)["suggested answer"] == "Q4"
    assert facts(event)["options"] == "Q3, Q4"


def test_a_pause_carrying_only_a_question_string_is_still_usable() -> None:
    class _Interrupt:
        value = "which quarter did you mean?"

    event = to_stage_event("__interrupt__", (_Interrupt(),))

    assert event.status == "paused"
    assert event.detail == "which quarter did you mean?"


# ── Ran, or did not run ─────────────────────────────────────────────────────


def test_a_stage_that_short_circuited_is_skipped_not_completed() -> None:
    """Critique returns an empty tuple when a turn is uncontested. Reported as
    `completed` it is indistinguishable from a critique that ran and found
    nothing, which is what let a client rank stages that had genuinely run
    below stages that had not."""
    event = to_stage_event("critique", {"critique_reports": ()})

    assert event.status == "skipped"
    assert event.detail is not None
    assert "contested" in event.detail


def test_probing_skipped_by_a_decisive_critique_says_so() -> None:
    event = to_stage_event("ambiguity_probing", {"probe_results": ()})

    assert event.status == "skipped"
    assert event.detail is not None
    assert "critique" in event.detail


def test_domain_scoping_distinguishes_an_override_from_no_match() -> None:
    """An empty delta means the caller supplied --domain-id; `None` means the
    scoper looked and found nothing. Both skip the work, for opposite reasons."""
    supplied = to_stage_event("domain_scoping", {})
    no_match = to_stage_event("domain_scoping", {"domain_id": None})
    scoped = to_stage_event("domain_scoping", {"domain_id": 3})

    assert supplied.status == "skipped"
    assert supplied.detail is not None
    assert "supplied" in supplied.detail
    assert no_match.status == "skipped"
    assert no_match.detail is not None
    assert "matched" in no_match.detail
    assert scoped.status == "completed"
    assert facts(scoped)["domain_id"] == "3"


def test_a_skipped_stage_carries_no_facts() -> None:
    """The reason is the whole value of a skipped event; a label with nothing
    beside it is noise in a rail that is already narrow."""
    event = to_stage_event("candidate_selection", {"selection": None})

    assert event.status == "skipped"
    assert event.facts == ()
