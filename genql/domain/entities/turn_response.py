"""What the CLI prints for one turn: a paused clarification, a short-circuited
non-SQL explanation, a query the cost gate refused to run, or a finished
answer.

One DTO rather than four because the CLI's job is the same in all four cases
— print something and exit 0 — and because a paused turn is not an error. The
thread_id is always set: even a turn that finishes in one shot has one, so a
follow-up question can attach to it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.execution_result import ExecutionResult


class TurnResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    thread_id: str
    clarifying_question: str | None = None
    intent: str | None = None
    validated_sql: str | None = None
    result: ExecutionResult | None = None
    applied_defaults: tuple[tuple[str, str], ...] = ()
    # Set, alongside a None `result`, exactly when the turn ended because the
    # query stayed over budget. This is the fourth outcome the CLI renders,
    # beside paused, short-circuited, and finished.
    narrowing_suggestion: str | None = None
    rewrite_rules_applied: tuple[str, ...] = ()
    # Provenance fields the HTTP DTO reads. Populated here with defaults in
    # Task 20 (the API layer needs them to exist); Task 22 fills them in from
    # graph state.
    plan_text: str | None = None
    referenced_objects: tuple[str, ...] = ()
    selection_method: str | None = None
    selection_rationale: str | None = None
    candidate_count: int = 0
    probe_count: int = 0
