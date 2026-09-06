"""Rejects functions that read files, sleep, open connections, or touch large
objects. An allowlist of permitted functions would be the stronger design and
is deliberately not what this is: the warehouse's own function set is open,
and blocking the named I/O escape hatches is what the parent spec §12 asks
for. Phase 7's optimizer is the natural place to revisit that trade.

Names are matched against the parsed AST rather than the SQL text so that
`/* pg_sleep */` in a comment and a column literally named `pg_sleep_seconds`
do not trip the rule.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.errors import StaticValidationError
from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.registry import GUARDRAILS

FORBIDDEN = frozenset(
    {
        "pg_sleep",
        "pg_sleep_for",
        "pg_sleep_until",
        "dblink",
        "dblink_connect",
        "dblink_exec",
        "pg_read_file",
        "pg_read_binary_file",
        "pg_ls_dir",
        "pg_stat_file",
        "lo_import",
        "lo_export",
        "lo_get",
        "lo_put",
        "query_to_xml",
        "pg_terminate_backend",
        "pg_cancel_backend",
        "pg_reload_conf",
    }
)


def _function_names(expression: exp.Expr) -> set[str]:
    names = {str(node.this).lower() for node in expression.find_all(exp.Anonymous)}
    for node in expression.find_all(exp.Func):
        if not isinstance(node, exp.Anonymous):
            names.add(node.sql_name().lower())
    return names


@GUARDRAILS.register("forbidden_function")
class ForbiddenFunctionGuardrail:
    name = "forbidden_function"
    priority = 20

    def __init__(self, config: GuardrailConfig) -> None:
        self._config = config

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        try:
            expression = sqlglot.parse_one(sql, dialect="postgres")
        except ParseError:
            # statement_kind (priority 10) owns parse failures and has already
            # reported this one with a better message.
            return ()
        offenders = sorted(_function_names(expression) & FORBIDDEN)
        if not offenders:
            return ()
        return (
            GuardrailViolation(
                rule_name=self.name,
                message=f"forbidden function(s) called: {', '.join(offenders)}",
            ),
        )

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        raise StaticValidationError((violation,))
