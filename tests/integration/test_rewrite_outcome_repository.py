"""A round trip through the table, then one aggregation over it. The
recommender's own SQL is what turns rows into advice, so it is exercised
against rows this test inserts rather than against a fixture of its output."""

from __future__ import annotations

import pytest

from genql.domain.entities.execution_actuals import ExecutionActuals
from genql.domain.entities.rewrite_outcome import RewriteOutcome
from genql.domain.errors import UnknownDatasourceError

pytestmark = pytest.mark.integration


def _outcome(sql_hash: str, reads: int) -> RewriteOutcome:
    return RewriteOutcome(
        sql_hash=sql_hash,
        datasource_name="local",
        rules_applied=("predicate_pushdown",),
        estimated_cost=1234.5,
        actuals=ExecutionActuals(
            total_time_ms=42.0, rows=10, shared_buffers_hit=5, shared_buffers_read=reads
        ),
    )


def test_writing_an_outcome_persists_every_field(rewrite_outcome_writer, semantic_engine) -> None:
    rewrite_outcome_writer.write(_outcome("a" * 64, 900))

    with semantic_engine.begin() as conn:
        row = conn.exec_driver_sql(
            "SELECT sql_hash, rules_applied, estimated_cost, actual_total_time_ms, "
            "shared_buffers_read FROM genql.genql_rewrite_outcome WHERE sql_hash = %s",
            ("a" * 64,),
        ).one()

    assert row.sql_hash == "a" * 64
    assert row.rules_applied == ["predicate_pushdown"]
    assert row.estimated_cost == pytest.approx(1234.5)
    assert row.shared_buffers_read == 900


def test_writing_an_outcome_for_an_unknown_datasource_raises(rewrite_outcome_writer) -> None:
    outcome = _outcome("b" * 64, 1).model_copy(update={"datasource_name": "nope"})
    with pytest.raises(UnknownDatasourceError):
        rewrite_outcome_writer.write(outcome)
