"""Reads and writes genql_thread — ownership and sidebar listing. `thread_id`
is never generated here: it always comes in already assigned, either by
`new_thread_id()` in query_turn.py or by an existing checkpoint, because the
checkpointer and this table must agree on the same id."""

from __future__ import annotations

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from genql.domain.entities.thread_summary import ThreadSummary
from genql.domain.errors import QueryError

_INSERT = text("""
    INSERT INTO genql.genql_thread (thread_id, user_id, datasource_name, title)
    VALUES (:thread_id, :user_id, :datasource_name, :title)
    ON CONFLICT (thread_id) DO NOTHING
""")
_TOUCH = text("""
    UPDATE genql.genql_thread SET last_active_at = now() WHERE thread_id = :thread_id
""")
_LIST_FOR_USER = text("""
    SELECT thread_id, user_id, datasource_name, title, created_at, last_active_at
    FROM genql.genql_thread WHERE user_id = :user_id ORDER BY last_active_at DESC
""")
_BY_ID = text("""
    SELECT thread_id, user_id, datasource_name, title, created_at, last_active_at
    FROM genql.genql_thread WHERE thread_id = :thread_id
""")


class SqlAlchemyThreadRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create(self, thread_id: str, user_id: str, datasource_name: str, title: str) -> None:
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    _INSERT,
                    {
                        "thread_id": thread_id,
                        "user_id": user_id,
                        "datasource_name": datasource_name,
                        "title": title,
                    },
                )
        except SQLAlchemyError as exc:
            raise QueryError(f"failed to create thread {thread_id!r}: {exc}") from exc

    def touch(self, thread_id: str) -> None:
        with self._engine.begin() as conn:
            conn.execute(_TOUCH, {"thread_id": thread_id})

    def list_for_user(self, user_id: str) -> tuple[ThreadSummary, ...]:
        with self._engine.connect() as conn:
            rows = conn.execute(_LIST_FOR_USER, {"user_id": user_id}).mappings().all()
        return tuple(ThreadSummary.model_validate(dict(row)) for row in rows)

    def by_id(self, thread_id: str) -> ThreadSummary | None:
        with self._engine.connect() as conn:
            row = conn.execute(_BY_ID, {"thread_id": thread_id}).mappings().first()
        return ThreadSummary.model_validate(dict(row)) if row else None
