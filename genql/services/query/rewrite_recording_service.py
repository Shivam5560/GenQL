"""Post-execution learning: what the planner predicted, beside what happened.

Reached only when `Settings.record_execution_actuals` is true, because
`EXPLAIN (ANALYZE, BUFFERS)` genuinely re-runs the statement — recording every
turn would double warehouse load for a diagnostic.

This service does not catch. Its caller (GuardedExecutionNode) does, because
the rule being enforced there is "a diagnostic must never fail a turn whose
query already succeeded", and that is a property of the call site, not of the
recording.
"""

from __future__ import annotations

import hashlib

from genql.domain.entities.rewrite_outcome import RewriteOutcome
from genql.domain.ports.execution_actuals_reader import ExecutionActualsReader
from genql.domain.ports.rewrite_outcome_writer import RewriteOutcomeWriter


class RewriteOutcomeRecordingService:
    def __init__(self, actuals: ExecutionActualsReader, writer: RewriteOutcomeWriter) -> None:
        self._actuals = actuals
        self._writer = writer

    def record(
        self,
        sql: str,
        rules_applied: tuple[str, ...],
        estimated_cost: float,
        datasource_name: str,
    ) -> None:
        measured = self._actuals.read_actuals(sql, datasource_name)
        self._writer.write(
            RewriteOutcome(
                sql_hash=hashlib.sha256(sql.encode()).hexdigest(),
                datasource_name=datasource_name,
                rules_applied=rules_applied,
                estimated_cost=estimated_cost,
                actuals=measured,
            )
        )
