"""Appends one rating. A plain insert: nothing here decides whether the
correction is valid — that judgment belongs to FeedbackService, which
runs before this is ever called."""

from __future__ import annotations

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from genql.domain.entities.feedback import Feedback
from genql.domain.errors import FeedbackError

_INSERT = text("""
    INSERT INTO genql.genql_feedback (thread_id, rating, corrected_sql, comment)
    VALUES (:thread_id, :rating, :corrected_sql, :comment)
""")


class PostgresFeedbackWriter:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def write(self, feedback: Feedback) -> None:
        try:
            with self._engine.begin() as conn:
                conn.execute(
                    _INSERT,
                    {
                        "thread_id": feedback.thread_id,
                        "rating": feedback.rating,
                        "corrected_sql": feedback.corrected_sql,
                        "comment": feedback.comment,
                    },
                )
        except SQLAlchemyError as exc:
            raise FeedbackError(f"failed to record feedback: {exc}") from exc
