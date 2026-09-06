"""The only place in Phase 5 that touches a database driver.

`SET LOCAL statement_timeout` is issued inside the same transaction as the
query rather than as a connection-level default, so a future probe execution
(Phase 6) can carry a stricter budget without a second connection pool.

One extra row beyond the cap is fetched and thrown away: that is how the
result knows it was truncated without counting the whole set, and it is why
`LIMIT` injection is a guardrail rather than this repository's job — the cap
here is the floor underneath whatever LIMIT the statement already carries.

Driver failures are translated here, not in the service, for the same reason
CatalogReader translates its own: a service that cannot import sqlalchemy
cannot catch a DBAPIError.
"""

from __future__ import annotations

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from genql.domain.entities.execution_result import ExecutionResult
from genql.domain.errors import ExecutionError


class ReadOnlyQueryExecutorRepository:
    def __init__(self, engine: Engine, statement_timeout_ms: int) -> None:
        self._engine = engine
        self._statement_timeout_ms = statement_timeout_ms

    def execute(self, sql: str, row_cap: int) -> ExecutionResult:
        try:
            with self._engine.begin() as conn:
                # statement_timeout is a GUC, not a bindable value; the int
                # cast is what makes the interpolation safe.
                timeout_ms = int(self._statement_timeout_ms)
                conn.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
                cursor = conn.execute(text(sql))
                columns = tuple(str(key) for key in cursor.keys())  # noqa: SIM118
                fetched = cursor.fetchmany(row_cap + 1)
        except SQLAlchemyError as exc:
            raise ExecutionError(f"failed to execute the validated statement: {exc}") from exc

        kept = fetched[:row_cap]
        return ExecutionResult(
            columns=columns,
            rows=tuple(tuple(row) for row in kept),
            row_count=len(kept),
            truncated=len(fetched) > row_cap,
        )
