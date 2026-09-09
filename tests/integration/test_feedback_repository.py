"""A round trip through the feedback table, then the database's own check
constraint rejecting a rating outside ('good', 'bad') — Pydantic's Literal
already refuses that value before it reaches the repository, so this proves
the database enforces it independently."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from genql.domain.entities.feedback import Feedback
from genql.domain.errors import FeedbackError
from genql.repositories.semantic.feedback_repository import PostgresFeedbackWriter

pytestmark = pytest.mark.integration


def test_writing_feedback_persists_every_column(migrated_engine: Engine) -> None:
    writer = PostgresFeedbackWriter(migrated_engine)
    feedback = Feedback(
        thread_id="t-round-trip",
        rating="bad",
        corrected_sql="SELECT 1",
        comment="close, but wrong join",
    )

    writer.write(feedback)

    with migrated_engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT thread_id, rating, corrected_sql, comment FROM genql.genql_feedback "
                "WHERE thread_id = :thread_id"
            ),
            {"thread_id": "t-round-trip"},
        ).one()

    assert row.thread_id == "t-round-trip"
    assert row.rating == "bad"
    assert row.corrected_sql == "SELECT 1"
    assert row.comment == "close, but wrong join"


def test_a_rating_outside_good_or_bad_is_rejected_by_the_database(
    migrated_engine: Engine,
) -> None:
    with pytest.raises(SQLAlchemyError), migrated_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO genql.genql_feedback (thread_id, rating) VALUES (:t, :r)"),
            {"t": "t-invalid", "r": "meh"},
        )


def test_a_database_failure_is_translated_to_feedback_error(migrated_engine: Engine) -> None:
    class _BrokenEngine:
        def begin(self):  # type: ignore[no-untyped-def]
            raise SQLAlchemyError("connection refused")

    writer = PostgresFeedbackWriter(_BrokenEngine())  # type: ignore[arg-type]

    with pytest.raises(FeedbackError):
        writer.write(Feedback(thread_id="t-1", rating="good"))
