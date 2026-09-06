"""Not a SQL-text check. It exists so "did every guardrail pass" is one
uniform report over one registry rather than four registered rules plus a
special case, and so a timeout misconfigured to zero fails loudly at
validation instead of silently letting a runaway query through."""

from __future__ import annotations

from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.repositories.guardrails.statement_timeout_guardrail import StatementTimeoutGuardrail


def _rule(statement_timeout_ms: int) -> StatementTimeoutGuardrail:
    return StatementTimeoutGuardrail(
        GuardrailConfig(
            row_cap=1000,
            statement_timeout_ms=statement_timeout_ms,
            allowed_objects=frozenset(),
        )
    )


def test_a_configured_timeout_passes_any_statement() -> None:
    assert _rule(30_000).check("SELECT id FROM shop.orders") == ()
    assert _rule(30_000).check("this is not sql at all") == ()


def test_a_zero_timeout_is_an_unrepairable_violation() -> None:
    violations = _rule(0).check("SELECT 1")

    assert len(violations) == 1
    assert violations[0].rule_name == "statement_timeout"
    assert violations[0].repairable is False


def test_a_negative_timeout_is_an_unrepairable_violation() -> None:
    assert _rule(-1).check("SELECT 1")[0].repairable is False


def test_repair_returns_the_statement_unchanged_because_sql_is_not_the_problem() -> None:
    rule = _rule(0)
    violation = rule.check("SELECT 1")[0]

    assert rule.repair("SELECT 1", violation) == "SELECT 1"


def test_the_rule_declares_its_name_and_priority() -> None:
    assert _rule(30_000).name == "statement_timeout"
    assert _rule(30_000).priority == 50
