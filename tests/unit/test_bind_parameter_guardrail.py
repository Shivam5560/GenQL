"""The rule that would have caught the UndefinedParameter at the cost gate.

`FAILING_STATEMENT` is the one a live turn produced and EXPLAIN refused,
pasted verbatim. It reached the cost gate having already paid for planning,
generation, validation, critique and probing, and the person asking saw a
Postgres error about a parameter they never wrote.
"""

from __future__ import annotations

import pytest

from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.bind_parameter_guardrail import BindParameterGuardrail

FAILING_STATEMENT = """
SELECT DISTINCT c.c_customer_sk AS c_customer_sk, c.c_customer_id AS c_customer_id
FROM tpcds.store_sales AS ss
JOIN tpcds.customer AS c ON c.c_customer_sk = ss.ss_customer_sk
JOIN tpcds.household_demographics AS hd
  ON c.c_current_hdemo_sk = hd.hd_demo_sk
  AND hd.hd_income_band_sk = ANY(CAST($1 AS INT[]))
WHERE TRUE
LIMIT 100
"""


def _rule() -> BindParameterGuardrail:
    return BindParameterGuardrail(
        GuardrailConfig(
            row_cap=1000,
            statement_timeout_ms=30_000,
            allowed_objects=frozenset({"tpcds.store_sales", "tpcds.customer"}),
        )
    )


def test_the_statement_the_cost_gate_refused_is_refused_here_first() -> None:
    violations = _rule().check(FAILING_STATEMENT)

    assert len(violations) == 1
    assert "$1" in violations[0].message


def test_the_violation_is_not_repairable_so_the_turn_regenerates() -> None:
    """Choosing the value the parameter stood for is generation, not rewriting."""
    assert all(not v.repairable for v in _rule().check(FAILING_STATEMENT))


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM tpcds.customer WHERE c_customer_sk = $1",
        "SELECT * FROM tpcds.customer WHERE c_customer_sk = ?",
        "SELECT * FROM tpcds.customer WHERE c_customer_sk = :customer",
        "SELECT * FROM tpcds.customer WHERE c_customer_sk = %s",
    ],
)
def test_every_placeholder_spelling_is_caught(sql: str) -> None:
    """sqlglot splits these across two node types — $1 is a Parameter and the
    rest are Placeholders — and catching three of four is not catching it."""
    assert _rule().check(sql) != ()


def test_each_distinct_parameter_is_named_once() -> None:
    message = (
        _rule().check("SELECT * FROM tpcds.customer WHERE a = $1 AND b = $2 AND c = $1")[0].message
    )

    assert "$1, $2" in message


def test_a_statement_with_literal_values_passes() -> None:
    sql = (
        "SELECT c.c_customer_id FROM tpcds.customer AS c "
        "JOIN tpcds.household_demographics AS hd ON c.c_current_hdemo_sk = hd.hd_demo_sk "
        "WHERE hd.hd_income_band_sk IN (18, 19, 20) LIMIT 100"
    )

    assert _rule().check(sql) == ()


def test_a_percent_sign_inside_a_like_pattern_is_not_a_placeholder() -> None:
    """`LIKE '%s%'` is a string literal, and rejecting it would fail correct
    SQL for a formatting reason."""
    sql = "SELECT * FROM tpcds.customer WHERE c_email_address LIKE '%something%' LIMIT 10"

    assert _rule().check(sql) == ()


def test_an_unparseable_statement_is_left_to_statement_kind() -> None:
    assert _rule().check("SELECT FROM WHERE ((") == ()
