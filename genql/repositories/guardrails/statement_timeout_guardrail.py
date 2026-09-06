"""Asserts the executor will actually apply a statement timeout.

The timeout itself is applied by ReadOnlyQueryExecutorRepository via
SET LOCAL, not here — a SQL-text rule cannot enforce a runtime setting. What
this rule contributes is that the setting is present and positive before
anything executes, reported through the same registry and the same
GuardrailViolation type as every other rule.
"""

from __future__ import annotations

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.registry import GUARDRAILS


@GUARDRAILS.register("statement_timeout")
class StatementTimeoutGuardrail:
    name = "statement_timeout"
    priority = 50

    def __init__(self, config: GuardrailConfig) -> None:
        self._statement_timeout_ms = config.statement_timeout_ms

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        if self._statement_timeout_ms > 0:
            return ()
        return (
            GuardrailViolation(
                rule_name=self.name,
                message=(
                    "query_statement_timeout_ms must be greater than zero; "
                    f"it is {self._statement_timeout_ms}"
                ),
            ),
        )

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        # Nothing about the SQL is wrong; the configuration is. Returning it
        # unchanged keeps the Guardrail contract total without pretending.
        return sql
