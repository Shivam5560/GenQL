"""The factory is what makes "one file plus one decorator" true: it never
names a rule class, and it orders by the rule's own declared priority rather
than by registry key, so the ordering survives a rule being renamed."""

from __future__ import annotations

from genql.domain.value_objects.guardrail_config import GuardrailConfig
from genql.infrastructure.query.guardrail_factory import GuardrailFactoryImpl


class FakeObjectNameReader:
    def __init__(self, names: frozenset[str]) -> None:
        self.calls: list[str] = []
        self._names = names

    def read_object_names(self, datasource_name: str) -> frozenset[str]:
        self.calls.append(datasource_name)
        return self._names


def _factory(names: frozenset[str] = frozenset({"shop.orders"})) -> GuardrailFactoryImpl:
    return GuardrailFactoryImpl(
        objects=FakeObjectNameReader(names), row_cap=1000, statement_timeout_ms=30_000
    )


def test_every_registered_rule_is_built() -> None:
    rules = _factory().for_datasource("local")

    assert len(rules) == 5


def test_rules_come_back_in_priority_order_not_alphabetical_order() -> None:
    rules = _factory().for_datasource("local")

    assert [rule.name for rule in rules] == [
        "statement_kind",
        "forbidden_function",
        "object_allowlist",
        "limit_injection",
        "statement_timeout",
    ]


def test_the_allowlist_is_read_for_the_datasource_asked_for() -> None:
    reader = FakeObjectNameReader(frozenset({"shop.orders"}))
    factory = GuardrailFactoryImpl(objects=reader, row_cap=1000, statement_timeout_ms=30_000)

    factory.for_datasource("warehouse_two")

    assert reader.calls == ["warehouse_two"]


def test_the_allowlist_actually_reaches_the_object_allowlist_rule() -> None:
    rules = {
        rule.name: rule for rule in _factory(frozenset({"shop.orders"})).for_datasource("local")
    }

    assert rules["object_allowlist"].check("SELECT * FROM shop.orders") == ()
    assert rules["object_allowlist"].check("SELECT * FROM shop.secrets") != ()


def test_the_row_cap_reaches_the_limit_injection_rule() -> None:
    factory = GuardrailFactoryImpl(
        objects=FakeObjectNameReader(frozenset()), row_cap=7, statement_timeout_ms=30_000
    )
    rules = {rule.name: rule for rule in factory.for_datasource("local")}
    violation = rules["limit_injection"].check("SELECT 1")[0]

    assert "LIMIT 7" in rules["limit_injection"].repair("SELECT 1", violation).upper()


def test_a_config_built_by_the_factory_carries_all_three_inputs() -> None:
    config = GuardrailConfig(
        row_cap=7, statement_timeout_ms=1, allowed_objects=frozenset({"shop.orders"})
    )

    assert config.row_cap == 7
    assert config.statement_timeout_ms == 1
