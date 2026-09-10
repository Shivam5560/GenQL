"""Rejects a candidate that expects values to be bound at execution time.

GenQL never binds anything. `ReadOnlyQueryExecutorRepository.execute` and
`PostgresCostEstimator` both call `conn.execute(text(sql))` with no parameter
map, by design — the statement a person reads in the SQL card is the statement
that runs, and a parameter would make those two different things.

So a candidate containing `$1`, `?`, `%s` or `:name` cannot ever run. Left
alone it dies at the cost gate with `UndefinedParameter: there is no parameter
$1`, having already paid for planning, generation, validation, critique and
probing — and the message a person sees is a Postgres error about a parameter
they never wrote.

The observed case: asked for customers in a high income bracket, the model
wrote `hd.hd_income_band_sk = ANY(CAST($1 AS INT[]))` — parameterising the
band list rather than deciding it. The fix is always the same and is always
available to the generator: inline the literal, or express the set as a
subquery against the dimension table.

sqlglot spells the two families differently — `$1` is `exp.Parameter`, while
`?`, `%s` and `:name` are all `exp.Placeholder` — so both are matched. Like
`surrogate_key_date`, this is unrepairable: choosing the value the parameter
stood for is the generator's job, not a rewrite.
"""

from __future__ import annotations

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.errors import StaticValidationError
from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.registry import GUARDRAILS


@GUARDRAILS.register("bind_parameter")
class BindParameterGuardrail:
    name = "bind_parameter"
    # Alongside the other "this statement cannot mean what it says" rules, and
    # before limit_injection (40), whose repair would otherwise rewrite a
    # statement about to be rejected anyway.
    priority = 36

    def __init__(self, config: GuardrailConfig) -> None:
        self._config = config

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        try:
            expression = sqlglot.parse_one(sql, dialect="postgres")
        except ParseError:
            # statement_kind (priority 10) owns parse failures.
            return ()

        found = [
            rendered
            for node in expression.find_all(exp.Parameter, exp.Placeholder)
            if (rendered := node.sql(dialect="postgres"))
        ]
        if not found:
            return ()
        # Deduplicated but order-preserving: `$1 ... $1 ... $2` is two
        # distinct parameters, and naming each one once is what the generator
        # needs in order to replace them all.
        named = ", ".join(dict.fromkeys(found))
        return (
            GuardrailViolation(
                rule_name=self.name,
                message=(
                    f"the statement expects bound parameters ({named}), and nothing binds "
                    "them — GenQL runs the statement exactly as written. Decide the value "
                    "and write it as a literal, or express the set as a subquery against "
                    "the table it comes from."
                ),
            ),
        )

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        raise StaticValidationError((violation,))
