"""The wire contract. Phase 9's frontend is written against this, so it is a
declared shape rather than whatever `TurnResponse.model_dump()` happens to
produce — and so that adding a field to the entity does not silently change
the API.

Tuples become lists because JSON has none, and a client round-tripping the
payload must get the same shape back.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from genql.domain.entities.turn_response import TurnResponse


class StartTurnRequest(BaseModel):
    question: str
    datasource: str
    domain_id: int | None = None
    thread_id: str | None = None


class ResumeTurnRequest(BaseModel):
    answer: str


class TurnResponseDto(BaseModel):
    thread_id: str
    clarifying_question: str | None = None
    intent: str | None = None
    validated_sql: str | None = None
    narrowing_suggestion: str | None = None
    columns: list[str] = []
    rows: list[list[Any]] = []
    row_count: int = 0
    truncated: bool = False
    applied_defaults: list[list[str]] = []
    rewrite_rules_applied: list[str] = []
    plan_text: str | None = None
    referenced_objects: list[str] = []
    selection_method: str | None = None
    selection_rationale: str | None = None
    candidate_count: int = 0
    probe_count: int = 0

    @classmethod
    def from_domain(cls, response: TurnResponse) -> TurnResponseDto:
        result = response.result
        return cls(
            thread_id=response.thread_id,
            clarifying_question=response.clarifying_question,
            intent=response.intent,
            validated_sql=response.validated_sql,
            narrowing_suggestion=response.narrowing_suggestion,
            columns=list(result.columns) if result else [],
            rows=[list(row) for row in result.rows] if result else [],
            row_count=result.row_count if result else 0,
            truncated=result.truncated if result else False,
            applied_defaults=[list(pair) for pair in response.applied_defaults],
            rewrite_rules_applied=list(response.rewrite_rules_applied),
            plan_text=response.plan_text,
            referenced_objects=list(response.referenced_objects),
            selection_method=response.selection_method,
            selection_rationale=response.selection_rationale,
            candidate_count=response.candidate_count,
            probe_count=response.probe_count,
        )
