"""The two safety properties that only a real database can prove: the
statement timeout actually aborts a slow query, and the row cap actually
truncates a result set larger than itself."""

from __future__ import annotations

import os

import pytest
from sqlalchemy import Engine
from sqlalchemy.engine import make_url

from genql.domain.errors import ExecutionError
from genql.infrastructure.db.engine import create_engine_from_dsn
from genql.repositories.query.query_executor_repository import ReadOnlyQueryExecutorRepository


@pytest.fixture()
def readonly_engine(migrated_engine: Engine, paradedb_dsn: str) -> Engine:
    url = make_url(paradedb_dsn).set(
        username="genql_readonly", password=os.environ["GENQL_READONLY_DB_PASSWORD"]
    )
    return create_engine_from_dsn(url.render_as_string(hide_password=False))


def test_rows_and_columns_come_back_in_order(readonly_engine: Engine) -> None:
    executor = ReadOnlyQueryExecutorRepository(readonly_engine, statement_timeout_ms=30_000)

    result = executor.execute("SELECT 1 AS a, 2 AS b", row_cap=10)

    assert result.columns == ("a", "b")
    assert result.rows == ((1, 2),)
    assert result.row_count == 1
    assert result.truncated is False


def test_the_row_cap_truncates_and_says_so(readonly_engine: Engine) -> None:
    executor = ReadOnlyQueryExecutorRepository(readonly_engine, statement_timeout_ms=30_000)

    result = executor.execute("SELECT n FROM generate_series(1, 50) AS n", row_cap=5)

    assert result.row_count == 5
    assert result.truncated is True
    assert result.rows[0] == (1,)


def test_an_exactly_full_result_is_not_reported_as_truncated(readonly_engine: Engine) -> None:
    executor = ReadOnlyQueryExecutorRepository(readonly_engine, statement_timeout_ms=30_000)

    result = executor.execute("SELECT n FROM generate_series(1, 5) AS n", row_cap=5)

    assert result.row_count == 5
    assert result.truncated is False


def test_the_statement_timeout_aborts_a_slow_query(readonly_engine: Engine) -> None:
    executor = ReadOnlyQueryExecutorRepository(readonly_engine, statement_timeout_ms=250)

    with pytest.raises(ExecutionError, match="timeout|canceling"):
        executor.execute("SELECT pg_sleep(5)", row_cap=10)


def test_a_write_attempt_is_translated_to_a_typed_error(readonly_engine: Engine) -> None:
    executor = ReadOnlyQueryExecutorRepository(readonly_engine, statement_timeout_ms=30_000)

    with pytest.raises(ExecutionError):
        executor.execute("CREATE TABLE should_not_exist (n int)", row_cap=10)
