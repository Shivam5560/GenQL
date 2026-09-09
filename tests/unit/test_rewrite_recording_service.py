"""The hash is the identity the recommender later aggregates on, so it is
asserted directly. Failure handling lives at the call site (the node), not
here — this service is allowed to raise, and the node is where the
"diagnostics must never fail a successful turn" rule is enforced."""

from __future__ import annotations

import hashlib

import pytest

from genql.domain.entities.execution_actuals import ExecutionActuals
from genql.domain.entities.rewrite_outcome import RewriteOutcome
from genql.services.query.rewrite_recording_service import RewriteOutcomeRecordingService

SQL = "SELECT count(*) FROM tpcds.store_sales"
ACTUALS = ExecutionActuals(
    total_time_ms=88.0, rows=1, shared_buffers_hit=10, shared_buffers_read=2000
)


class _Reader:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def read_actuals(self, sql: str, datasource_name: str) -> ExecutionActuals:
        self.calls.append((sql, datasource_name))
        return ACTUALS


class _Writer:
    def __init__(self) -> None:
        self.written: list[RewriteOutcome] = []

    def write(self, outcome: RewriteOutcome) -> None:
        self.written.append(outcome)


class _RaisingReader:
    def read_actuals(self, sql: str, datasource_name: str) -> ExecutionActuals:
        raise RuntimeError("explain analyze failed")


def test_recording_hashes_the_executed_statement() -> None:
    writer = _Writer()
    RewriteOutcomeRecordingService(_Reader(), writer).record(
        SQL, ("predicate_pushdown",), 1234.0, "local"
    )

    assert writer.written[0].sql_hash == hashlib.sha256(SQL.encode()).hexdigest()


def test_recording_carries_the_rules_and_the_estimate_beside_the_actuals() -> None:
    writer = _Writer()
    RewriteOutcomeRecordingService(_Reader(), writer).record(
        SQL, ("predicate_pushdown", "projection_pruning"), 1234.0, "local"
    )

    outcome = writer.written[0]
    assert outcome.rules_applied == ("predicate_pushdown", "projection_pruning")
    assert outcome.estimated_cost == 1234.0
    assert outcome.actuals.shared_buffers_read == 2000
    assert outcome.datasource_name == "local"


def test_the_actuals_are_measured_against_the_statement_that_ran() -> None:
    reader = _Reader()
    RewriteOutcomeRecordingService(reader, _Writer()).record(SQL, (), 1.0, "local")

    assert reader.calls == [(SQL, "local")]


def test_a_reader_failure_propagates_for_the_caller_to_swallow() -> None:
    with pytest.raises(RuntimeError):
        RewriteOutcomeRecordingService(_RaisingReader(), _Writer()).record(SQL, (), 1.0, "local")
