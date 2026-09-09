"""Upgrade to head creates the feedback table with the columns the
repository reads, and the `rating` check constraint rejects anything other
than 'good' or 'bad' at the database, not just in Pydantic."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import DataError, IntegrityError

pytestmark = pytest.mark.integration

EXPECTED_COLUMNS = {
    "id",
    "thread_id",
    "rating",
    "corrected_sql",
    "comment",
    "created_at",
}


def test_upgrade_creates_the_feedback_table(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)
    columns = {c["name"] for c in inspector.get_columns("genql_feedback", schema="genql")}

    assert columns >= EXPECTED_COLUMNS


def test_the_table_is_indexed_by_thread(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)
    indexes = inspector.get_indexes("genql_feedback", schema="genql")

    assert any("thread_id" in index["column_names"] for index in indexes)


def test_the_rating_check_constraint_rejects_a_third_value(migrated_engine: Engine) -> None:
    with pytest.raises((IntegrityError, DataError)), migrated_engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO genql.genql_feedback (thread_id, rating) VALUES (%s, %s)",
            ("t-1", "maybe"),
        )
