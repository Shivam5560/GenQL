"""Every table and view the statement reads must be in the semantic store.

An unqualified table name is matched against the bare object name in the
allowlist rather than rejected: candidate generation is prompted with
`schema.object` names, but sqlglot's rendering of a single-schema query can
drop the qualifier, and rejecting that would fail valid SQL for a formatting
reason. A name that matches nothing at all — qualified or not — is a
hallucinated object and is refused.

CTE names are collected first and excluded: `WITH recent AS (...) SELECT FROM
recent` reads no table called `recent`.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.errors import StaticValidationError
from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.registry import GUARDRAILS


@GUARDRAILS.register("object_allowlist")
class ObjectAllowlistGuardrail:
    name = "object_allowlist"
    priority = 30

    def __init__(self, config: GuardrailConfig) -> None:
        self._allowed = config.allowed_objects
        self._bare = {name.split(".", 1)[-1] for name in config.allowed_objects}

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        try:
            expression = sqlglot.parse_one(sql, dialect="postgres")
        except ParseError:
            return ()

        cte_names = {str(cte.alias_or_name).lower() for cte in expression.find_all(exp.CTE)}
        offenders = sorted(
            {
                referenced
                for referenced in self._referenced_objects(expression)
                if referenced not in cte_names and not self._is_allowed(referenced)
            }
        )
        if not offenders:
            return ()
        return (
            GuardrailViolation(
                rule_name=self.name,
                message=(
                    f"object(s) not in the semantic store for this datasource: "
                    f"{', '.join(offenders)}"
                ),
            ),
        )

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        raise StaticValidationError((violation,))

    @staticmethod
    def _referenced_objects(expression: exp.Expr) -> set[str]:
        names: set[str] = set()
        for table in expression.find_all(exp.Table):
            schema_name = str(table.db).lower()
            object_name = str(table.name).lower()
            names.add(f"{schema_name}.{object_name}" if schema_name else object_name)
        return names

    def _is_allowed(self, referenced: str) -> bool:
        if "." in referenced:
            return referenced in self._allowed
        return referenced in self._bare
