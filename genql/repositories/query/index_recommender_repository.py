"""Turns accumulated outcomes into index advice for a human.

The signal is buffer *reads* (pages fetched from disk) rather than total time:
time varies with cache state and concurrency, while a statement that
repeatedly reads many pages is repeatedly scanning something. The threshold
lives in the SQL rather than in configuration because it is a property of what
"repeatedly scanning" means, not a knob an operator should be tuning before
there is evidence about what a good value is.

Columns come from parsing each recorded statement's WHERE clause with sqlglot,
not from the plan text: the plan names a filter expression, the AST names the
column, and only the second can be joined against the catalog.
"""

from __future__ import annotations

import sqlglot
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlglot import exp

from genql.domain.entities.index_recommendation import IndexRecommendation
from genql.domain.errors import OptimizationError

_MIN_EXECUTIONS = 3
_MIN_BUFFER_READS = 1_000

_SELECT_HEAVY = text("""
    SELECT o.sql_hash, count(*) AS executions, max(o.shared_buffers_read) AS reads
    FROM genql.genql_rewrite_outcome o
    JOIN genql.genql_datasource d ON d.name = o.datasource_id
    WHERE d.name = :datasource_name AND o.shared_buffers_read >= :min_reads
    GROUP BY o.sql_hash
    HAVING count(*) >= :min_executions
    ORDER BY max(o.shared_buffers_read) DESC
""")


class PostgresIndexRecommender:
    """Reads evidence and proposes indexes. Never creates one — the parent
    spec's §11 is explicit that GenQL reports and a human acts."""

    def __init__(self, engine: Engine, statements: dict[str, str] | None = None) -> None:
        # `statements` maps sql_hash -> statement text. The outcome table
        # stores the hash, not the text, so the recommender is constructed
        # with whatever the caller can supply; an empty map yields no
        # recommendations rather than a wrong one.
        self._engine = engine
        self._statements = statements or {}

    def recommend(self, datasource_name: str) -> tuple[IndexRecommendation, ...]:
        try:
            with self._engine.begin() as conn:
                rows = conn.execute(
                    _SELECT_HEAVY,
                    {
                        "datasource_name": datasource_name,
                        "min_reads": _MIN_BUFFER_READS,
                        "min_executions": _MIN_EXECUTIONS,
                    },
                ).all()
        except SQLAlchemyError as exc:
            raise OptimizationError(f"failed to read rewrite outcomes: {exc}") from exc

        recommendations: list[IndexRecommendation] = []
        for row in rows:
            statement = self._statements.get(row.sql_hash)
            if statement is None:
                continue
            for table, column in _filtered_columns(statement):
                recommendations.append(
                    IndexRecommendation(
                        object_qualified_name=f"{datasource_name}.{table}",
                        column_name=column,
                        rationale=(
                            f"{row.executions} recorded executions filtered this column while "
                            f"reading {row.reads} shared buffer pages from disk"
                        ),
                        supporting_execution_count=int(row.executions),
                    )
                )
        return tuple(recommendations)


def _filtered_columns(statement: str) -> list[tuple[str, str]]:
    try:
        expression = sqlglot.parse_one(statement, dialect="postgres")
    except sqlglot.errors.ParseError:
        return []
    found: list[tuple[str, str]] = []
    for where in expression.find_all(exp.Where):
        for column in where.find_all(exp.Column):
            table = column.table or ""
            if table and column.name:
                found.append((table, column.name))
    return found
