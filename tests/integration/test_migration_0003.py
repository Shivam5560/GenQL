"""0003 re-keys the catalog. It must not lose rows discovered under 0002."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text


@pytest.fixture()
def at_0002(engine: Engine, paradedb_dsn: str) -> Iterator[Config]:
    """Rewind to 0002, plant a row, and hand back the config to upgrade with."""
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", paradedb_dsn)
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "0002")
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO genql.genql_object "
                "(schema_name, object_name, object_type, row_estimate) "
                "VALUES ('legacy', 'orders', 'TABLE', 42)"
            )
        )
    yield cfg
    command.upgrade(cfg, "head")


def test_upgrade_backfills_existing_rows_to_the_local_datasource(
    at_0002: Config, engine: Engine
) -> None:
    command.upgrade(at_0002, "0003")

    with engine.connect() as conn:
        datasource_name = conn.execute(
            text("SELECT datasource_name FROM genql.genql_object WHERE object_name = 'orders'")
        ).scalar_one()
        registered = conn.execute(
            text("SELECT count(*) FROM genql.genql_schema WHERE schema_name = 'legacy'")
        ).scalar_one()
        dsn_env_var = conn.execute(
            text("SELECT dsn_env_var FROM genql.genql_datasource WHERE name = 'local'")
        ).scalar_one()

    assert datasource_name == "local"
    assert registered == 1
    assert dsn_env_var == "GENQL_WAREHOUSE_DSN"


def test_removing_a_datasource_cascades_to_its_catalog(at_0002: Config, engine: Engine) -> None:
    command.upgrade(at_0002, "0003")

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM genql.genql_datasource WHERE name = 'local'"))
    with engine.connect() as conn:
        remaining = conn.execute(text("SELECT count(*) FROM genql.genql_object")).scalar_one()

    assert remaining == 0


def test_downgrade_removes_the_new_tables_and_column(at_0002: Config, engine: Engine) -> None:
    command.upgrade(at_0002, "0003")
    command.downgrade(at_0002, "0002")

    with engine.connect() as conn:
        assert (
            conn.execute(text("SELECT to_regclass('genql.genql_datasource')")).scalar_one() is None
        )
        has_column = conn.execute(
            text(
                "SELECT count(*) FROM information_schema.columns "
                "WHERE table_schema = 'genql' AND table_name = 'genql_object' "
                "AND column_name = 'datasource_name'"
            )
        ).scalar_one()
    assert has_column == 0
