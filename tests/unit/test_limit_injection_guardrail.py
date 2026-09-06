"""Parent spec §12: mandatory LIMIT injection. The only repairable rule in the
registry — a missing LIMIT is a defect with exactly one correct fix, unlike
every other violation, which needs different SQL rather than more SQL."""

from __future__ import annotations

from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.limit_injection_guardrail import LimitInjectionGuardrail

CONFIG = GuardrailConfig(row_cap=1000, statement_timeout_ms=30_000, allowed_objects=frozenset())


def _rule() -> LimitInjectionGuardrail:
    return LimitInjectionGuardrail(CONFIG)


def test_a_statement_with_a_limit_passes() -> None:
    assert _rule().check("SELECT id FROM shop.orders LIMIT 10") == ()


def test_a_missing_limit_is_a_repairable_violation() -> None:
    violations = _rule().check("SELECT id FROM shop.orders")

    assert len(violations) == 1
    assert violations[0].rule_name == "limit_injection"
    assert violations[0].repairable is True


def test_repair_injects_the_configured_row_cap_and_the_result_re_passes() -> None:
    rule = _rule()
    violation = rule.check("SELECT id FROM shop.orders")[0]

    repaired = rule.repair("SELECT id FROM shop.orders", violation)

    assert "LIMIT 1000" in repaired.upper()
    assert rule.check(repaired) == ()


def test_repair_leaves_the_projection_and_predicate_intact() -> None:
    rule = _rule()
    sql = "SELECT o.id FROM shop.orders AS o WHERE o.total > 5"
    violation = rule.check(sql)[0]

    repaired = rule.repair(sql, violation)

    assert "o.total > 5" in repaired
    assert "o.id" in repaired


def test_a_union_without_a_limit_is_repaired_too() -> None:
    rule = _rule()
    sql = "SELECT 1 UNION ALL SELECT 2"
    violation = rule.check(sql)[0]

    assert rule.check(rule.repair(sql, violation)) == ()


def test_unparseable_sql_is_left_to_statement_kind() -> None:
    assert _rule().check("SELECT FROM WHERE ((") == ()


def test_the_rule_declares_its_name_and_priority() -> None:
    assert _rule().name == "limit_injection"
    assert _rule().priority == 40
