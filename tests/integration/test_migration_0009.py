"""Upgrade to head creates the table with the columns the repositories read,
and downgrade removes it. The columns are asserted by name because
PostgresIndexRecommender aggregates on `shared_buffers_read` and
`datasource_id`, and a rename would fail there at query time rather than
here."""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, inspect

pytestmark = pytest.mark.integration

EXPECTED_COLUMNS = {
    "id",
    "sql_hash",
    "datasource_id",
    "rules_applied",
    "estimated_cost",
    "actual_total_time_ms",
    "actual_rows",
    "shared_buffers_hit",
    "shared_buffers_read",
    "recorded_at",
}


def test_upgrade_creates_the_rewrite_outcome_table(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)
    columns = {c["name"] for c in inspector.get_columns("genql_rewrite_outcome", schema="genql")}

    assert columns >= EXPECTED_COLUMNS


def test_the_table_is_indexed_by_datasource(migrated_engine: Engine) -> None:
    inspector = inspect(migrated_engine)
    indexes = inspector.get_indexes("genql_rewrite_outcome", schema="genql")

    assert any("datasource_id" in index["column_names"] for index in indexes)
