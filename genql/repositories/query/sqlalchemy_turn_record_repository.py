"""Reads and writes genql_turn — the UI's read model for a thread's history.
ExecutionResult and applied_defaults round-trip as JSON columns; nothing
here interprets their contents, matching this layer's job everywhere else
in the codebase (move bytes, don't reason about them)."""

from __future__ import annotations

import json

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.entities.turn_record import TurnRecord
from genql.domain.errors import QueryError

_INSERT = text("""
    INSERT INTO genql.genql_turn
        (turn_id, thread_id, sequence, question, recap, validated_sql,
         clarifying_question, result_json, applied_defaults_json)
    VALUES
        (:turn_id, :thread_id, :sequence, :question, :recap, :validated_sql,
         :clarifying_question, CAST(:result_json AS JSON), CAST(:applied_defaults_json AS JSON))
""")
_LIST_FOR_THREAD = text("""
    SELECT turn_id, thread_id, sequence, question, recap, validated_sql,
           clarifying_question, result_json, applied_defaults_json, created_at
    FROM genql.genql_turn WHERE thread_id = :thread_id ORDER BY sequence ASC
""")


class SqlAlchemyTurnRecordRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def append(self, record: TurnRecord) -> None:
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    _INSERT,
                    {
                        "turn_id": record.turn_id,
                        "thread_id": record.thread_id,
                        "sequence": record.sequence,
                        "question": record.question,
                        "recap": record.recap,
                        "validated_sql": record.validated_sql,
                        "clarifying_question": record.clarifying_question,
                        "result_json": (
                            json.dumps(record.result.model_dump(mode="json"))
                            if record.result
                            else None
                        ),
                        "applied_defaults_json": json.dumps(
                            [list(pair) for pair in record.applied_defaults]
                        ),
                    },
                )
        except SQLAlchemyError as exc:
            raise QueryError(f"failed to append turn record {record.turn_id!r}: {exc}") from exc

    def list_for_thread(self, thread_id: str) -> tuple[TurnRecord, ...]:
        with self._engine.connect() as conn:
            rows = conn.execute(_LIST_FOR_THREAD, {"thread_id": thread_id}).mappings().all()
        return tuple(self._to_entity(row) for row in rows)

    @staticmethod
    def _to_entity(row: object) -> TurnRecord:
        data = dict(row)  # type: ignore[call-overload]
        result_json = data.pop("result_json")
        defaults_json = data.pop("applied_defaults_json")
        return TurnRecord(
            **data,
            result=ExecutionResult.model_validate(result_json) if result_json else None,
            applied_defaults=tuple((pair[0], pair[1]) for pair in (defaults_json or [])),
        )
