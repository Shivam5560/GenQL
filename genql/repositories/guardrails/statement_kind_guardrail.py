"""Only SELECT and WITH survive. Runs first (priority 10) so a DELETE is
rejected for being a DELETE rather than for happening to name a table the
allowlist has never heard of.

Parse failures are reported here too: this is the first rule to touch the
statement, so a candidate that is not SQL at all gets one clean violation
instead of five confused ones.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.errors import StaticValidationError
from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.registry import GUARDRAILS

_ALLOWED = (exp.Select, exp.Union, exp.Subquery)


@GUARDRAILS.register("statement_kind")
class StatementKindGuardrail:
    name = "statement_kind"
    priority = 10

    def __init__(self, config: GuardrailConfig) -> None:
        self._config = config

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        try:
            expression = sqlglot.parse_one(sql, dialect="postgres")
        except ParseError as exc:
            return (
                GuardrailViolation(
                    rule_name=self.name, message=f"could not parse the candidate: {exc}"
                ),
            )
        if isinstance(expression, _ALLOWED):
            return ()
        return (
            GuardrailViolation(
                rule_name=self.name,
                message=(
                    f"{type(expression).__name__.upper()} is not permitted; "
                    "only SELECT and WITH statements may be executed"
                ),
            ),
        )

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        raise StaticValidationError((violation,))
