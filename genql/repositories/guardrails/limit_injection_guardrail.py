"""Injects the configured row cap when the statement has no LIMIT of its own.

Only the outermost statement is checked. A LIMIT inside a subquery bounds that
subquery, not the result set the caller receives, so treating it as sufficient
would defeat the cap. An existing outer LIMIT is left alone even when it is
larger than the cap: the executor's own row cap is the floor underneath it, so
the statement never returns more than the cap regardless.
"""

from __future__ import annotations

from typing import cast

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.registry import GUARDRAILS


@GUARDRAILS.register("limit_injection")
class LimitInjectionGuardrail:
    name = "limit_injection"
    priority = 40

    def __init__(self, config: GuardrailConfig) -> None:
        self._row_cap = config.row_cap

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        expression = self._parse(sql)
        if expression is None or expression.args.get("limit") is not None:
            return ()
        return (
            GuardrailViolation(
                rule_name=self.name,
                message=f"no LIMIT on the outermost statement; {self._row_cap} will be injected",
                repairable=True,
            ),
        )

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        expression = self._parse(sql)
        if expression is None:
            return sql
        limited = expression.limit(self._row_cap)  # type: ignore[attr-defined]
        return cast(str, limited.sql(dialect="postgres"))

    @staticmethod
    def _parse(sql: str) -> exp.Expr | None:
        try:
            return sqlglot.parse_one(sql, dialect="postgres")
        except ParseError:
            # statement_kind (priority 10) owns parse failures.
            return None
