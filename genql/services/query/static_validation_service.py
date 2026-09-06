"""Runs every registered guardrail, repairs what is repairable, qualifies last.

Order matters and is not the spec's literal order. `qualify` raises on a
non-SELECT, so qualifying first would turn a clean `statement_kind` violation
("DELETE is not permitted") into an opaque optimizer error from the one rule
whose entire purpose is to report exactly that. The statement is therefore
parsed, run past every rule in priority order, and only then qualified.

Each repairable violation gets exactly one repair attempt, after which the
rule re-checks its own work. A rule whose repair does not actually fix
anything fails on the re-check instead of looping — which is the property the
graph's single-retry edge depends on to terminate.

`sqlglot` is a pure parser: no I/O, no driver, no network. Importing it here
does not breach the no-database-in-services rule, and it is deliberately not
added to either import-linter forbidden list.
"""

from __future__ import annotations

import sqlglot
from sqlglot.errors import OptimizeError, ParseError
from sqlglot.optimizer.qualify import qualify

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import StaticValidationError
from genql.domain.ports.guardrail import Guardrail
from genql.domain.ports.guardrail_factory import GuardrailFactory


class StaticValidationService:
    def __init__(self, guardrails: GuardrailFactory) -> None:
        self._guardrails = guardrails

    def validate(self, candidate: SqlCandidate, datasource_name: str) -> str:
        sql = candidate.sql
        for rule in self._guardrails.for_datasource(datasource_name):
            sql = self._apply(rule, sql)
        return self._qualify(sql)

    @staticmethod
    def _apply(rule: Guardrail, sql: str) -> str:
        violations = rule.check(sql)
        if not violations:
            return sql

        unrepairable = tuple(v for v in violations if not v.repairable)
        if unrepairable:
            raise StaticValidationError(unrepairable)

        for violation in violations:
            sql = rule.repair(sql, violation)

        remaining = rule.check(sql)
        if remaining:
            raise StaticValidationError(remaining)
        return sql

    @staticmethod
    def _qualify(sql: str) -> str:
        try:
            expression = sqlglot.parse_one(sql, dialect="postgres")
            # qualify_columns needs a real column schema to be meaningful and
            # would reject valid SQL without one; qualifying tables is the part
            # that matters here. identify=False keeps the output readable
            # instead of quoting every identifier.
            qualified = qualify(
                expression,
                dialect="postgres",
                qualify_columns=False,
                validate_qualify_columns=False,
                identify=False,
            )
        except (ParseError, OptimizeError) as exc:
            raise StaticValidationError(
                (
                    GuardrailViolation(
                        rule_name="qualify",
                        message=f"the statement could not be parsed or qualified: {exc}",
                    ),
                )
            ) from exc
        return str(qualified.sql(dialect="postgres"))
