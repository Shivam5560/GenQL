"""The service knows nothing about any individual rule: it asks the factory
for them, runs them in the order given, and gives each repairable violation
exactly one chance. The termination test is the important one — a rule whose
repair does not actually fix anything must not loop."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import StaticValidationError
from genql.domain.ports.guardrail import Guardrail
from genql.infrastructure.query.guardrail_factory import GuardrailFactoryImpl
from genql.services.query.static_validation_service import StaticValidationService

PLAN = QueryPlan(question="q", plan_text="p", referenced_objects=("local.shop.orders",))


def _candidate(sql: str) -> SqlCandidate:
    return SqlCandidate(sql=sql, plan=PLAN)


class RecordingRule:
    name = "recording"
    priority = 10

    def __init__(self) -> None:
        self.checked: list[str] = []

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        self.checked.append(sql)
        return ()

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        raise AssertionError("repair must not be called for a clean statement")


class UnrepairableRule:
    name = "unrepairable"
    priority = 20

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        return (GuardrailViolation(rule_name=self.name, message="nope", repairable=False),)

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        raise AssertionError("repair must not be called for an unrepairable violation")


class UselessRepairRule:
    """Reports a repairable violation whose repair changes nothing."""

    name = "useless_repair"
    priority = 30

    def __init__(self) -> None:
        self.repairs = 0

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        return (GuardrailViolation(rule_name=self.name, message="still bad", repairable=True),)

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        self.repairs += 1
        return sql


class SuffixRepairRule:
    name = "suffix_repair"
    priority = 40

    def check(self, sql: str) -> tuple[GuardrailViolation, ...]:
        if sql.endswith("LIMIT 5"):
            return ()
        return (GuardrailViolation(rule_name=self.name, message="needs a cap", repairable=True),)

    def repair(self, sql: str, violation: GuardrailViolation) -> str:
        return f"{sql} LIMIT 5"


class FixedFactory:
    def __init__(self, rules: Sequence[Guardrail]) -> None:
        self._rules = rules

    def for_datasource(self, datasource_name: str) -> Sequence[Guardrail]:
        return self._rules


class FakeObjectNameReader:
    def read_object_names(self, datasource_name: str) -> frozenset[str]:
        return frozenset({"shop.orders"})


def test_a_clean_candidate_comes_back_qualified() -> None:
    rule = RecordingRule()
    service = StaticValidationService(FixedFactory([rule]))

    validated = service.validate(_candidate("SELECT o.id FROM shop.orders AS o LIMIT 5"), "local")

    assert "shop.orders" in validated
    assert rule.checked == ["SELECT o.id FROM shop.orders AS o LIMIT 5"]


def test_an_unrepairable_violation_raises_and_carries_the_violation() -> None:
    service = StaticValidationService(FixedFactory([UnrepairableRule()]))

    with pytest.raises(StaticValidationError) as caught:
        service.validate(_candidate("SELECT 1 LIMIT 1"), "local")

    assert caught.value.violations[0].rule_name == "unrepairable"


def test_a_repair_is_attempted_exactly_once_and_then_the_loop_stops() -> None:
    rule = UselessRepairRule()
    service = StaticValidationService(FixedFactory([rule]))

    with pytest.raises(StaticValidationError):
        service.validate(_candidate("SELECT 1 LIMIT 1"), "local")

    assert rule.repairs == 1


def test_a_successful_repair_is_carried_into_the_returned_sql() -> None:
    service = StaticValidationService(FixedFactory([SuffixRepairRule()]))

    validated = service.validate(_candidate("SELECT 1"), "local")

    assert "LIMIT 5" in validated.upper()


def test_unparseable_sql_raises_rather_than_reaching_qualify() -> None:
    service = StaticValidationService(FixedFactory([]))

    with pytest.raises(StaticValidationError):
        service.validate(_candidate("SELECT FROM WHERE (("), "local")


def test_the_real_registry_rejects_a_delete_via_statement_kind() -> None:
    """§9's stated case: the rule that reports a DELETE must be statement_kind,
    which is only true because the factory orders by priority."""
    factory = GuardrailFactoryImpl(
        objects=FakeObjectNameReader(), row_cap=1000, statement_timeout_ms=30_000
    )
    service = StaticValidationService(factory)

    with pytest.raises(StaticValidationError) as caught:
        service.validate(_candidate("DELETE FROM shop.orders"), "local")

    assert caught.value.violations[0].rule_name == "statement_kind"


def test_the_real_registry_rejects_pg_sleep_unrepairably() -> None:
    factory = GuardrailFactoryImpl(
        objects=FakeObjectNameReader(), row_cap=1000, statement_timeout_ms=30_000
    )
    service = StaticValidationService(factory)

    with pytest.raises(StaticValidationError) as caught:
        service.validate(_candidate("SELECT pg_sleep(5) LIMIT 1"), "local")

    assert caught.value.violations[0].rule_name == "forbidden_function"
    assert caught.value.violations[0].repairable is False


def test_the_real_registry_repairs_a_missing_limit_and_the_candidate_passes() -> None:
    factory = GuardrailFactoryImpl(
        objects=FakeObjectNameReader(), row_cap=1000, statement_timeout_ms=30_000
    )
    service = StaticValidationService(factory)

    validated = service.validate(_candidate("SELECT o.id FROM shop.orders AS o"), "local")

    assert "LIMIT 1000" in validated.upper()
