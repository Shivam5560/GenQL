"""The wire contract for GET /threads and GET /threads/{id}."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel

from genql.domain.entities.thread_summary import ThreadSummary
from genql.domain.entities.turn_record import TurnRecord


class ThreadSummaryDto(BaseModel):
    thread_id: str
    datasource_name: str
    title: str
    created_at: datetime
    last_active_at: datetime

    @classmethod
    def from_domain(cls, summary: ThreadSummary) -> ThreadSummaryDto:
        return cls(
            thread_id=summary.thread_id,
            datasource_name=summary.datasource_name,
            title=summary.title,
            created_at=summary.created_at,
            last_active_at=summary.last_active_at,
        )


class TurnRecordDto(BaseModel):
    turn_id: str
    sequence: int
    question: str
    recap: str | None = None
    validated_sql: str | None = None
    clarifying_question: str | None = None
    columns: list[str] = []
    rows: list[list[Any]] = []
    row_count: int = 0
    applied_defaults: list[list[str]] = []
    created_at: datetime

    @classmethod
    def from_domain(cls, record: TurnRecord) -> TurnRecordDto:
        result = record.result
        return cls(
            turn_id=record.turn_id,
            sequence=record.sequence,
            question=record.question,
            recap=record.recap,
            validated_sql=record.validated_sql,
            clarifying_question=record.clarifying_question,
            columns=list(result.columns) if result else [],
            rows=[list(row) for row in result.rows] if result else [],
            row_count=result.row_count if result else 0,
            applied_defaults=[list(pair) for pair in record.applied_defaults],
            created_at=record.created_at,
        )


class ThreadDetailDto(BaseModel):
    summary: ThreadSummaryDto
    turns: list[TurnRecordDto]
