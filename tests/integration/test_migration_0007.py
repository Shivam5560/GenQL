"""0007 is one additive table. The upgrade/downgrade pair is asserted the same
way 0005's and 0006's are: the table exists after `head`, the unique constraint
that the upsert names exists by that exact name, the datasource FK cascades,
and stepping back to 0006 removes it cleanly.

LangGraph's own checkpoint tables are deliberately NOT asserted here — they are
created by PostgresSaver.setup(), not by Alembic, because they are langgraph's
schema to evolve across its own releases. tests/integration/test_postgres_
checkpointer.py covers them.
"""

from __future__ import annotations

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError


@pytest.fixture()
def alembic_config(paradedb_dsn: str) -> Config:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", paradedb_dsn)
    return cfg


def test_upgrade_creates_genql_rule(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as conn:
        present = conn.execute(
            text("SELECT to_regclass('genql.genql_rule') IS NOT NULL")
        ).scalar_one()

    assert present


def test_the_identity_constraint_is_named_for_the_upsert(migrated_engine: Engine) -> None:
    """PostgresRuleWriter says ON CONFLICT ON CONSTRAINT uq_genql_rule_identity."""
    with migrated_engine.connect() as conn:
        present = conn.execute(
            text("SELECT count(*) FROM pg_constraint WHERE conname = 'uq_genql_rule_identity'")
        ).scalar_one()

    assert present == 1


def test_a_rule_row_requires_a_registered_datasource(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as conn, pytest.raises(IntegrityError):
        conn.execute(
            text(
                "INSERT INTO genql.genql_rule "
                "(datasource_name, name, dimension, value, description) "
                "VALUES ('no-such-datasource', 'r', 'time_range', 'v', 'd')"
            )
        )


def test_deleting_the_datasource_cascades_to_its_rules(
    migrated_engine: Engine, register_schema: object
) -> None:
    register_schema("cascade_ds", "public")  # type: ignore[operator]
    with migrated_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO genql.genql_rule "
                "(datasource_name, name, dimension, value, description) "
                "VALUES ('cascade_ds', 'r', 'time_range', 'v', 'd')"
            )
        )
        conn.execute(text("DELETE FROM genql.genql_datasource WHERE name = 'cascade_ds'"))
        remaining = conn.execute(
            text("SELECT count(*) FROM genql.genql_rule WHERE datasource_name = 'cascade_ds'")
        ).scalar_one()

    assert remaining == 0


def test_downgrade_to_0006_drops_genql_rule_and_upgrade_restores_it(
    migrated_engine: Engine, alembic_config: Config
) -> None:
    command.downgrade(alembic_config, "0006")
    with migrated_engine.connect() as conn:
        gone = conn.execute(text("SELECT to_regclass('genql.genql_rule') IS NULL")).scalar_one()
    assert gone

    command.upgrade(alembic_config, "head")
    with migrated_engine.connect() as conn:
        back = conn.execute(text("SELECT to_regclass('genql.genql_rule') IS NOT NULL")).scalar_one()
    assert back
