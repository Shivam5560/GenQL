"""Rules behave exactly like metrics: YAML-authored, upserted by natural key,
read back in a deterministic order. The ordering is asserted because the
ambiguity gate takes the FIRST rule for a dimension when two rules claim the
same one, so an unordered read would make which default wins depend on
physical row order.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import Engine, text

from genql.domain.entities.rule import Rule
from genql.repositories.semantic.rule_repository import PostgresRuleReader, PostgresRuleWriter

DS = "rules_ds"

FISCAL = Rule(
    name="default_period",
    dimension="time_range",
    value="fiscal_year_to_date",
    description="An unqualified period means the fiscal year to date.",
)
ACTIVE = Rule(
    name="active_only",
    dimension="filter",
    value="status = 'active'",
    description="Customers means active customers unless stated otherwise.",
)


@pytest.fixture()
def seeded(migrated_engine: Engine, register_schema: Callable[[str, str], None]) -> Engine:
    register_schema(DS, "public")
    with migrated_engine.begin() as conn:
        conn.execute(text("DELETE FROM genql.genql_rule WHERE datasource_name = :ds"), {"ds": DS})
    return migrated_engine


def test_written_rules_read_back_ordered_by_name(seeded: Engine) -> None:
    PostgresRuleWriter(seeded).write_rules(DS, (FISCAL, ACTIVE))

    rules = PostgresRuleReader(seeded).read_rules(DS)

    assert [r.name for r in rules] == ["active_only", "default_period"]
    assert rules[1].value == "fiscal_year_to_date"


def test_writing_the_same_name_twice_updates_rather_than_duplicates(seeded: Engine) -> None:
    writer = PostgresRuleWriter(seeded)
    writer.write_rules(DS, (FISCAL,))

    writer.write_rules(
        DS,
        (
            Rule(
                name="default_period",
                dimension="time_range",
                value="trailing_twelve_months",
                description="Changed.",
            ),
        ),
    )

    rules = PostgresRuleReader(seeded).read_rules(DS)
    assert len(rules) == 1
    assert rules[0].value == "trailing_twelve_months"
    assert rules[0].description == "Changed."


def test_writing_no_rules_is_a_no_op_returning_zero(seeded: Engine) -> None:
    assert PostgresRuleWriter(seeded).write_rules(DS, ()) == 0


def test_write_returns_the_number_written(seeded: Engine) -> None:
    assert PostgresRuleWriter(seeded).write_rules(DS, (FISCAL, ACTIVE)) == 2


def test_rules_are_scoped_to_their_datasource(
    seeded: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("other_rules_ds", "public")
    PostgresRuleWriter(seeded).write_rules(DS, (FISCAL,))

    assert PostgresRuleReader(seeded).read_rules("other_rules_ds") == ()
