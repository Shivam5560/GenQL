"""Parent spec §12: statement kind restricted to SELECT and WITH. No DDL, DML,
or DCL — and nothing here is repairable, because rewriting a DELETE into a
SELECT would be guessing at intent, not repairing a defect."""

from __future__ import annotations

import pytest

from genql.domain.errors import StaticValidationError
from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.statement_kind_guardrail import StatementKindGuardrail

CONFIG = GuardrailConfig(row_cap=1000, statement_timeout_ms=30_000, allowed_objects=frozenset())


def _rule() -> StatementKindGuardrail:
    return StatementKindGuardrail(CONFIG)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "SELECT s.name FROM shop.store AS s WHERE s.id = 1 LIMIT 10",
        "WITH t AS (SELECT 1 AS n) SELECT n FROM t",
        "SELECT 1 UNION ALL SELECT 2",
        "(SELECT 1)",
    ],
)
def test_select_and_with_statements_pass(sql: str) -> None:
    assert _rule().check(sql) == ()


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM shop.store",
        "INSERT INTO shop.store (id) VALUES (1)",
        "UPDATE shop.store SET id = 2",
        "DROP TABLE shop.store",
        "CREATE TABLE t (n int)",
        "GRANT SELECT ON shop.store TO someone",
        "COPY shop.store FROM '/etc/passwd'",
    ],
)
def test_every_other_statement_kind_is_rejected_and_unrepairable(sql: str) -> None:
    violations = _rule().check(sql)

    assert len(violations) == 1
    assert violations[0].rule_name == "statement_kind"
    assert violations[0].repairable is False


def test_unparseable_sql_is_reported_here_rather_than_crashing() -> None:
    violations = _rule().check("SELECT FROM WHERE ((")

    assert len(violations) == 1
    assert "parse" in violations[0].message.lower()
    assert violations[0].repairable is False


def test_repair_refuses_because_nothing_here_is_repairable() -> None:
    violation = _rule().check("DELETE FROM shop.store")[0]

    with pytest.raises(StaticValidationError):
        _rule().repair("DELETE FROM shop.store", violation)


def test_the_rule_declares_its_name_and_priority() -> None:
    assert _rule().name == "statement_kind"
    assert _rule().priority == 10
