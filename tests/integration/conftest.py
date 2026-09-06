from __future__ import annotations

import os
from collections.abc import Callable, Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, text
from testcontainers.postgres import PostgresContainer

from genql.infrastructure.db.engine import create_engine_from_dsn


@pytest.fixture(scope="session")
def paradedb_dsn() -> Iterator[str]:
    """Prefer a running stack; fall back to an ephemeral container.

    GENQL_TEST_DSN points at the compose stack on the Debian VM. Testcontainers
    against a remote daemon over SSH works but spends minutes per container on
    readiness polling across the link, so it is the fallback, not the default.
    """
    dsn = os.environ.get("GENQL_TEST_DSN")
    if dsn:
        yield dsn
        return

    container = PostgresContainer(
        image="paradedb/paradedb:0.25.6-pg18",
        username="genql",
        password="genql",
        dbname="genql",
        driver="psycopg",
    )
    with container as running:
        yield running.get_connection_url()


@pytest.fixture(scope="session")
def engine(paradedb_dsn: str) -> Engine:
    eng = create_engine_from_dsn(paradedb_dsn)
    with eng.begin() as conn:
        # Order matters: pg_search declares a dependency on vector and fails without it.
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_search"))
    return eng


@pytest.fixture(scope="session")
def migrated_engine(engine: Engine, paradedb_dsn: str) -> Engine:
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", paradedb_dsn)
    command.upgrade(cfg, "head")
    return engine


@pytest.fixture()
def register_schema(migrated_engine: Engine) -> Callable[[str, str], None]:
    """Register (datasource, schema) so catalog writes satisfy their foreign key.

    Task 9 gives the CLI `genql schema add`; until then, and for tests that are
    not exercising the CLI, registration is a direct insert.
    """

    def _register(datasource_name: str, schema_name: str) -> None:
        with migrated_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO genql.genql_datasource (name, dialect, dsn_env_var) "
                    "VALUES (:ds, 'postgres', 'GENQL_WAREHOUSE_DSN') "
                    "ON CONFLICT (name) DO NOTHING"
                ),
                {"ds": datasource_name},
            )
            conn.execute(
                text(
                    "INSERT INTO genql.genql_schema (datasource_name, schema_name) "
                    "VALUES (:ds, :schema) ON CONFLICT ON CONSTRAINT pk_genql_schema DO NOTHING"
                ),
                {"ds": datasource_name, "schema": schema_name},
            )

    return _register


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "skipif_no_tpcds: skip unless the tpcds schema has been seeded"
    )


@pytest.fixture(autouse=True)
def _skip_without_tpcds(request: pytest.FixtureRequest, engine: Engine) -> None:
    if request.node.get_closest_marker("skipif_no_tpcds") is None:
        return
    with engine.connect() as conn:
        seeded = conn.execute(
            text("SELECT to_regclass('tpcds.store_sales') IS NOT NULL")
        ).scalar_one()
    if not seeded:
        pytest.skip("tpcds schema not seeded; run data/seed_tpcds.py")
