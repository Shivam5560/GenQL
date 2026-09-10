"""One turn, start to finish or start to pause.

This is where the graph's raw output mapping becomes a typed TurnResponse, and
it is the only place that knows an interrupted invoke returns a
`__interrupt__` key rather than raising. Keeping that knowledge in one file
means a langgraph release that changed the convention breaks here, once.

The lock wraps the invoke, not the whole command, and it is a `with` block so
release survives an exception, an interrupt, and a clean finish alike — one
thread, one in-flight turn, per the parent spec's §13.

A thread id is generated when the caller does not supply one, because even a
turn that finishes without pausing needs one for a follow-up to attach to.
"""

from __future__ import annotations

import uuid
import uuid as _uuid
from datetime import UTC, datetime
from typing import Any, cast

from genql.api.query_graph import resume_query, run_query
from genql.api.query_state import QueryState
from genql.domain.entities.stage_event import StageEvent
from genql.domain.entities.turn_record import TurnRecord
from genql.domain.entities.turn_response import TurnResponse
from genql.domain.ports.thread_lock import ThreadLockFactory
from genql.domain.ports.thread_repository import ThreadRepository
from genql.domain.ports.turn_record_repository import TurnRecordRepository
from genql.infrastructure.tracing.qa_span import qa_span

_TITLE_MAX_LEN = 80


def new_thread_id() -> str:
    return f"t-{uuid.uuid4().hex}"


def stored_trace_parent(graph: Any, thread_id: str) -> str | None:
    """The traceparent a pending turn on this thread recorded when it started.

    None for a thread with no checkpoint (or one predating this field) — the
    caller then opens a fresh trace rather than a child of nothing.
    """
    values = graph.get_state({"configurable": {"thread_id": thread_id}}).values
    return values.get("trace_parent") if values else None


def _applied_defaults(raw: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    ambiguity = raw.get("ambiguity")
    if ambiguity is None:
        return ()
    # Tupled rather than passed through: a checkpoint round-trip can restore
    # the pairs as JSON arrays, and TurnResponse declares tuples.
    return tuple((dimension, rule) for dimension, rule in ambiguity.applied_defaults)


def _assumed(raw: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    ambiguity = raw.get("ambiguity")
    if ambiguity is None:
        return ()
    return tuple((dimension, value) for dimension, value in ambiguity.assumed)


def _clarification(value: Any) -> tuple[str, str | None, tuple[str, ...]]:
    """Unpack AmbiguityInterruptNode's interrupt payload.

    A mapping since suggestions were added, and a bare string before that —
    both are handled because a turn checkpointed by the older code can be
    resumed by this one, and a dict rendered through `str()` would show the
    user a Python repr instead of a question.
    """
    if isinstance(value, dict):
        options = value.get("options") or ()
        suggested = value.get("suggested_answer")
        return (
            str(value.get("question", "")),
            str(suggested) if suggested else None,
            tuple(str(option) for option in options),
        )
    return str(value), None, ()


def to_response(thread_id: str, raw: dict[str, Any]) -> TurnResponse:
    interrupts = raw.get("__interrupt__") or ()
    if interrupts:
        question, suggested, options = _clarification(interrupts[0].value)
        return TurnResponse(
            thread_id=thread_id,
            clarifying_question=question,
            suggested_answer=suggested,
            clarification_options=options,
            applied_defaults=_applied_defaults(raw),
            assumed=_assumed(raw),
        )
    state = cast(QueryState, raw)
    optimization = state.get("optimization")
    over_budget = optimization is not None and not optimization.within_budget
    # An intent is reported only when it stopped the turn. An over-budget turn
    # also has no result, so it must be excluded here or a perfectly
    # well-classified analytical question would be reported as the wrong kind
    # of question.
    short_circuited = state["validated_sql"] is None and state["result"] is None and not over_budget
    plan = state.get("plan")
    selection = state.get("selection")
    return TurnResponse(
        thread_id=thread_id,
        intent=state["intent"] if short_circuited else None,
        validated_sql=state["validated_sql"],
        result=state["result"],
        applied_defaults=_applied_defaults(raw),
        assumed=_assumed(raw),
        narrowing_suggestion=(
            optimization.narrowing_suggestion if optimization is not None and over_budget else None
        ),
        rewrite_rules_applied=optimization.rules_applied if optimization else (),
        plan_text=plan.plan_text if plan is not None else None,
        referenced_objects=plan.referenced_objects if plan is not None else (),
        selection_method=selection.method if selection is not None else None,
        selection_rationale=selection.rationale if selection is not None else None,
        candidate_count=len(state.get("candidates") or ()),
        probe_count=len(state.get("probe_results") or ()),
    )


def record_turn(  # noqa: PLR0913, PLR0917 - one field per TurnRecord input
    threads: ThreadRepository,
    turn_records: TurnRecordRepository,
    thread_id: str,
    user_id: str,
    datasource_name: str | None,
    question: str,
    response: TurnResponse,
    stages: tuple[StageEvent, ...] = (),
) -> None:
    """Persist one finished turn, creating the thread on its first.

    Public because both transports must record identically: the streaming
    endpoint calls this immediately before its terminal event, so a turn the
    user watched arrive is in their history when they reload the page.

    `stages` is the turn's pipeline trail. Only the streaming transport has
    one — the blocking path never generates stage events — so a turn asked
    there records an empty trail, which every reader treats as "no discussion
    recorded", the same as a row written before they were stored.
    """
    existing = turn_records.list_for_thread(thread_id)
    sequence = len(existing)
    if sequence == 0:
        assert datasource_name is not None  # the first turn on a thread always has one
        threads.create(thread_id, user_id, datasource_name, question[:_TITLE_MAX_LEN])
    else:
        threads.touch(thread_id)
    turn_records.append(
        TurnRecord(
            turn_id=f"tr-{_uuid.uuid4().hex}",
            thread_id=thread_id,
            sequence=sequence,
            question=question,
            validated_sql=response.validated_sql,
            clarifying_question=response.clarifying_question,
            result=response.result,
            applied_defaults=response.applied_defaults,
            stages=stages,
            created_at=datetime.now(UTC),
        )
    )


def start_turn(  # noqa: PLR0913, PLR0917 - mirrors the graph's own start parameters
    graph: Any,
    locks: ThreadLockFactory,
    question: str,
    datasource_name: str,
    domain_id: int | None = None,
    thread_id: str | None = None,
    *,
    user_id: str | None = None,
    threads: ThreadRepository | None = None,
    turn_records: TurnRecordRepository | None = None,
) -> TurnResponse:
    resolved = thread_id or new_thread_id()
    # The trace's root, opened before the lock so a turn that waited on
    # another turn shows the wait as its own time rather than as nothing.
    with qa_span(question, datasource_name, resolved) as trace_parent, locks.for_thread(resolved):
        raw = run_query(graph, question, datasource_name, resolved, domain_id, trace_parent)
    response = to_response(resolved, raw)
    if user_id is not None and threads is not None and turn_records is not None:
        record_turn(threads, turn_records, resolved, user_id, datasource_name, question, response)
    return response


def resume_turn(  # noqa: PLR0913, PLR0917 - mirrors the graph's own resume parameters
    graph: Any,
    locks: ThreadLockFactory,
    answer: str,
    thread_id: str,
    *,
    user_id: str | None = None,
    threads: ThreadRepository | None = None,
    turn_records: TurnRecordRepository | None = None,
) -> TurnResponse:
    # Fetched before the span opens: this completes the SAME turn that
    # started the trace, not a new question, so the span must join that
    # trace rather than root one of its own.
    parent = stored_trace_parent(graph, thread_id)
    with qa_span(answer, None, thread_id, parent=parent), locks.for_thread(thread_id):
        raw = resume_query(graph, answer, thread_id)
    response = to_response(thread_id, raw)
    if user_id is not None and threads is not None and turn_records is not None:
        record_turn(threads, turn_records, thread_id, user_id, None, answer, response)
    return response
