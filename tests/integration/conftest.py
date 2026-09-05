from __future__ import annotations

import os
from collections.abc import Iterator

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
