"""One executed statement's predicted cost beside its measured cost.

`sql_hash` rather than the statement text is the natural key: the table
accumulates one row per execution, the same question asked twice produces the
same statement, and aggregating by hash is what lets IndexRecommender say "3
of 3 recorded executions" rather than "3 statements that look similar".
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.execution_actuals import ExecutionActuals


class RewriteOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)

    sql_hash: str
    datasource_name: str
    rules_applied: tuple[str, ...]
    estimated_cost: float
    actuals: ExecutionActuals
