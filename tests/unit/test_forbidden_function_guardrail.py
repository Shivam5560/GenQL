"""Parent spec §12: pg_sleep, dblink, pg_read_file, large-object functions,
and anything else performing I/O. COPY is not listed here on purpose — it is a
statement kind, and statement_kind already rejects it with a better message."""

from __future__ import annotations

import pytest

from genql.domain.errors import StaticValidationError
from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.forbidden_function_guardrail import ForbiddenFunctionGuardrail

CONFIG = GuardrailConfig(row_cap=1000, statement_timeout_ms=30_000, allowed_objects=frozenset())


def _rule() -> ForbiddenFunctionGuardrail:
    return ForbiddenFunctionGuardrail(CONFIG)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT pg_sleep(5)",
        "SELECT PG_SLEEP(5)",
        "SELECT * FROM dblink('dbname=x', 'SELECT 1') AS t(n int)",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT lo_import('/etc/passwd')",
        "SELECT n FROM t WHERE n = (SELECT pg_sleep(1))",
    ],
)
def test_forbidden_functions_are_rejected_and_unrepairable(sql: str) -> None:
    violations = _rule().check(sql)

    assert len(violations) == 1
    assert violations[0].rule_name == "forbidden_function"
    assert violations[0].repairable is False


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT count(*) FROM shop.store",
        "SELECT sum(o.total) FROM shop.orders AS o",
        "SELECT date_trunc('day', o.created_at) FROM shop.orders AS o",
    ],
)
def test_ordinary_functions_pass(sql: str) -> None:
    assert _rule().check(sql) == ()


def test_the_message_names_the_offending_function() -> None:
    violations = _rule().check("SELECT pg_sleep(5)")

    assert "pg_sleep" in violations[0].message


def test_unparseable_sql_is_left_to_statement_kind() -> None:
    assert _rule().check("SELECT FROM WHERE ((") == ()


def test_repair_refuses_because_nothing_here_is_repairable() -> None:
    violation = _rule().check("SELECT pg_sleep(5)")[0]

    with pytest.raises(StaticValidationError):
        _rule().repair("SELECT pg_sleep(5)", violation)


def test_the_rule_declares_its_name_and_priority() -> None:
    assert _rule().name == "forbidden_function"
    assert _rule().priority == 20
