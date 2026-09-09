"""A stage delta becomes one short line, never the delta itself: a delta can
carry every schema link or every candidate statement, and putting that on the
wire would make the event stream the widest interface in the system."""

from __future__ import annotations

from genql.api.sse.stage_events import to_stage_event
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink


def test_a_completed_node_becomes_a_completed_event_named_for_the_node() -> None:
    event = to_stage_event(
        "planning",
        {
            "plan": QueryPlan(
                question="q", plan_text="sum sales by month", referenced_objects=("local.a.b",)
            )
        },
    )

    assert event.stage == "planning"
    assert event.status == "completed"


def test_a_schema_linking_delta_is_summarized_by_count_not_by_content() -> None:
    links = tuple(SchemaLink(object_qualified_name=f"local.s.o{i}") for i in range(12))

    event = to_stage_event("schema_linking", {"links": links})

    assert event.detail is not None
    assert "12" in event.detail
    assert "o11" not in event.detail


def test_an_interrupt_becomes_a_paused_event() -> None:
    class _Interrupt:
        value = "which quarter did you mean?"

    event = to_stage_event("__interrupt__", (_Interrupt(),))

    assert event.status == "paused"
    assert event.detail == "which quarter did you mean?"


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
