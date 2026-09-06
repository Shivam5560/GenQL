"""Parent spec §12: object allowlist enforced against the semantic store. A
table GenQL has never catalogued is not a table this statement may read, which
is what stops a hallucinated join from reaching the warehouse at all."""

from __future__ import annotations

import pytest

from genql.domain.errors import StaticValidationError
from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.object_allowlist_guardrail import ObjectAllowlistGuardrail

CONFIG = GuardrailConfig(
    row_cap=1000,
    statement_timeout_ms=30_000,
    allowed_objects=frozenset({"shop.orders", "shop.customers"}),
)


def _rule() -> ObjectAllowlistGuardrail:
    return ObjectAllowlistGuardrail(CONFIG)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM shop.orders",
        "SELECT * FROM SHOP.ORDERS",
        "SELECT o.id FROM shop.orders AS o JOIN shop.customers AS c ON c.id = o.customer_id",
        "SELECT * FROM orders",
    ],
)
def test_catalogued_objects_pass(sql: str) -> None:
    assert _rule().check(sql) == ()


def test_a_cte_name_is_not_treated_as_a_table() -> None:
    sql = "WITH recent AS (SELECT * FROM shop.orders) SELECT * FROM recent"

    assert _rule().check(sql) == ()


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM shop.secrets",
        "SELECT * FROM pg_catalog.pg_authid",
        "SELECT o.id FROM shop.orders AS o JOIN other.thing AS t ON t.id = o.id",
    ],
)
def test_uncatalogued_objects_are_rejected_and_unrepairable(sql: str) -> None:
    violations = _rule().check(sql)

    assert len(violations) == 1
    assert violations[0].rule_name == "object_allowlist"
    assert violations[0].repairable is False


def test_the_message_names_every_offending_object() -> None:
    violations = _rule().check("SELECT * FROM shop.secrets, other.thing")

    assert "shop.secrets" in violations[0].message
    assert "other.thing" in violations[0].message


def test_unparseable_sql_is_left_to_statement_kind() -> None:
    assert _rule().check("SELECT FROM WHERE ((") == ()


def test_repair_refuses_because_nothing_here_is_repairable() -> None:
    violation = _rule().check("SELECT * FROM shop.secrets")[0]

    with pytest.raises(StaticValidationError):
        _rule().repair("SELECT * FROM shop.secrets", violation)


def test_the_rule_declares_its_name_and_priority() -> None:
    assert _rule().name == "object_allowlist"
    assert _rule().priority == 30
