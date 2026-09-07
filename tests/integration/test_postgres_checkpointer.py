"""The checkpointer, proven against real Postgres — the only thing that can
prove it, since its whole job is durability across processes.

The round trip is run through a two-node toy graph rather than through GenQL's
real graph on purpose: this asserts the SAVER, and a failure here should point
at langgraph wiring rather than at schema linking. tests/integration/
test_phase6_end_to_end.py runs the same round trip through the real pipeline.
"""

from __future__ import annotations

from typing import Any, TypedDict

import pytest
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt
from sqlalchemy import Engine, text

from genql.domain.entities.schema_link import SchemaLink
from genql.infrastructure.checkpoint.postgres_checkpointer import build_checkpointer
from genql.infrastructure.db.psycopg_dsn import to_libpq_dsn

CHECKPOINT_TABLES = ("checkpoints", "checkpoint_blobs", "checkpoint_writes")


class ToyState(TypedDict):
    question: str
    answer: str | None
    passes: int


def gate(state: ToyState) -> dict[str, Any]:
    if state["answer"] is None:
        return {"answer": interrupt("which time range?"), "passes": state["passes"] + 1}
    return {"passes": state["passes"] + 1}


@pytest.fixture()
def saver(paradedb_dsn: str, migrated_engine: Engine) -> Any:
    return build_checkpointer(to_libpq_dsn(paradedb_dsn), max_size=2)


@pytest.fixture()
def toy_graph(saver: Any) -> Any:
    graph: StateGraph[ToyState] = StateGraph(ToyState)
    graph.add_node("gate", gate)
    graph.add_edge(START, "gate")
    graph.add_edge("gate", END)
    return graph.compile(checkpointer=saver)


@pytest.mark.parametrize("table", CHECKPOINT_TABLES)
def test_setup_creates_langgraphs_own_tables(
    saver: Any, migrated_engine: Engine, table: str
) -> None:
    """Created by PostgresSaver.setup(), not by Alembic — migration 0007
    deliberately does not own langgraph's schema."""
    with migrated_engine.connect() as conn:
        present = conn.execute(
            text("SELECT to_regclass(:t) IS NOT NULL"), {"t": table}
        ).scalar_one()

    assert present


def test_building_the_checkpointer_twice_is_idempotent(
    paradedb_dsn: str, migrated_engine: Engine
) -> None:
    """setup() runs on every build; a second build must not fail on tables the
    first one already created, because a reset_singletons() in any test does
    exactly this."""
    build_checkpointer(to_libpq_dsn(paradedb_dsn), max_size=2)
    build_checkpointer(to_libpq_dsn(paradedb_dsn), max_size=2)


def test_an_interrupted_run_returns_the_question_without_raising(toy_graph: Any) -> None:
    config = {"configurable": {"thread_id": "cp-interrupt"}}

    out = toy_graph.invoke({"question": "revenue", "answer": None, "passes": 0}, config)

    assert out["__interrupt__"][0].value == "which time range?"
    assert out["answer"] is None


def test_resuming_with_a_command_produces_the_answered_state(toy_graph: Any) -> None:
    config = {"configurable": {"thread_id": "cp-resume"}}
    toy_graph.invoke({"question": "revenue", "answer": None, "passes": 0}, config)

    out = toy_graph.invoke(Command(resume="last quarter"), config)

    assert "__interrupt__" not in out
    assert out["answer"] == "last quarter"
    assert out["question"] == "revenue"


def test_the_resumed_node_re_executes_from_its_first_line(saver: Any) -> None:
    """LangGraph resumes a node by re-running it, not by continuing after the
    interrupt() call. Every node this phase adds is written to be idempotent
    under that, and this pins the behaviour so a langgraph upgrade that changed
    it would be caught here rather than in production.

    Re-execution is asserted through a side-effect log rather than through the
    state, because the interrupted pass commits NOTHING: interrupt() raises out
    of the node, so the update it was building is discarded. That is the second
    half of what idempotency has to survive, so it is asserted too — `passes`
    reaches 1, not 2, even though the body ran twice.
    """
    entered_with: list[str | None] = []

    def counting_gate(state: ToyState) -> dict[str, Any]:
        entered_with.append(state["answer"])
        return gate(state)

    graph: StateGraph[ToyState] = StateGraph(ToyState)
    graph.add_node("gate", counting_gate)
    graph.add_edge(START, "gate")
    graph.add_edge("gate", END)
    compiled = graph.compile(checkpointer=saver)

    config = {"configurable": {"thread_id": "cp-reexec"}}
    compiled.invoke({"question": "revenue", "answer": None, "passes": 0}, config)

    out = compiled.invoke(Command(resume="last quarter"), config)

    # Twice, and the resumed pass sees the same pre-interrupt state as the first.
    assert entered_with == [None, None]
    assert out["passes"] == 1
    assert out["answer"] == "last quarter"


def test_a_second_saver_over_the_same_database_sees_the_checkpointed_state(
    paradedb_dsn: str, migrated_engine: Engine
) -> None:
    """The durability claim, stated as a test: a checkpoint written by one
    saver must resume through a DIFFERENT saver, because a resumed `genql
    query` is a brand-new process."""
    config = {"configurable": {"thread_id": "cp-cross-process"}}

    def build() -> Any:
        graph: StateGraph[ToyState] = StateGraph(ToyState)
        graph.add_node("gate", gate)
        graph.add_edge(START, "gate")
        graph.add_edge("gate", END)
        return graph.compile(
            checkpointer=build_checkpointer(to_libpq_dsn(paradedb_dsn), max_size=2)
        )

    build().invoke({"question": "revenue", "answer": None, "passes": 0}, config)
    out = build().invoke(Command(resume="last quarter"), config)

    assert out["answer"] == "last quarter"


class LinkState(TypedDict):
    link: SchemaLink | None


def _set_link(state: LinkState) -> dict[str, Any]:
    return {"link": SchemaLink(object_qualified_name="local.shop.orders", column_names=("id",))}


def test_a_custom_entity_type_beyond_ambiguity_assessment_round_trips_as_itself(
    saver: Any,
) -> None:
    """SchemaLink is one of the QueryState entity types the review found
    missing from allowed_msgpack_modules. Restrictive mode does not raise on
    an unlisted type — it silently comes back as a plain dict, with only a
    warning logged — so the failure mode this guards against is a passing
    test suite next to corrupted state, not a crash."""
    graph: StateGraph[LinkState] = StateGraph(LinkState)
    graph.add_node("set_link", _set_link)
    graph.add_edge(START, "set_link")
    graph.add_edge("set_link", END)
    compiled = graph.compile(checkpointer=saver)

    config = {"configurable": {"thread_id": "cp-entity-roundtrip"}}
    compiled.invoke({"link": None}, config)

    restored = compiled.get_state(config).values["link"]

    assert isinstance(restored, SchemaLink)
    assert restored.object_qualified_name == "local.shop.orders"
    assert restored.column_names == ("id",)


def test_threads_do_not_see_each_others_state(toy_graph: Any) -> None:
    toy_graph.invoke(
        {"question": "revenue", "answer": None, "passes": 0},
        {"configurable": {"thread_id": "cp-a"}},
    )
    toy_graph.invoke(
        {"question": "headcount", "answer": None, "passes": 0},
        {"configurable": {"thread_id": "cp-b"}},
    )

    out = toy_graph.invoke(Command(resume="last quarter"), {"configurable": {"thread_id": "cp-a"}})

    assert out["question"] == "revenue"
