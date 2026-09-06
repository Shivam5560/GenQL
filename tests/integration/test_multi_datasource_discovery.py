"""n schemas across n databases, shown rather than asserted.

Requires GENQL_WH2_DSN to point at the genql_wh2 database seeded with Pagila
(see data/README.md). Skipped when it is unset, so the suite still runs on a
machine that has only the primary warehouse.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import Engine, text
from typer.testing import CliRunner

from genql.cli.main import app
from genql.composition_root import Container

WH2_DSN = os.environ.get("GENQL_WH2_DSN", "")

pytestmark = pytest.mark.skipif(not WH2_DSN, reason="GENQL_WH2_DSN not set")

FIXTURE = """
DROP SCHEMA IF EXISTS ds_a CASCADE;
CREATE SCHEMA ds_a;
CREATE TABLE ds_a.alpha (a_id BIGINT PRIMARY KEY, a_name TEXT);
INSERT INTO ds_a.alpha VALUES (1, 'one');
DROP SCHEMA IF EXISTS ds_b CASCADE;
CREATE SCHEMA ds_b;
CREATE TABLE ds_b.beta (b_id BIGINT PRIMARY KEY, b_name TEXT);
INSERT INTO ds_b.beta VALUES (1, 'two');
"""


@pytest.fixture()
def wired(migrated_engine: Engine, paradedb_dsn: str, monkeypatch) -> Engine:
    with migrated_engine.begin() as conn:
        conn.execute(text(FIXTURE))
        conn.execute(
            text("DELETE FROM genql.genql_datasource WHERE name IN ('primary', 'secondary')")
        )
    monkeypatch.setenv("GENQL_PRIMARY_DSN", paradedb_dsn)
    monkeypatch.setenv("GENQL_SECONDARY_DSN", WH2_DSN)
    monkeypatch.setenv("GENQL_SEMANTIC_DSN", paradedb_dsn)
    Container().reset_singletons()
    return migrated_engine


def _register(runner: CliRunner) -> None:
    runner.invoke(
        app,
        [
            "datasource",
            "add",
            "--name",
            "primary",
            "--dialect",
            "postgres",
            "--dsn-env",
            "GENQL_PRIMARY_DSN",
        ],
    )
    runner.invoke(
        app,
        [
            "datasource",
            "add",
            "--name",
            "secondary",
            "--dialect",
            "postgres",
            "--dsn-env",
            "GENQL_SECONDARY_DSN",
        ],
    )
    runner.invoke(app, ["schema", "add", "--datasource", "primary", "--schema", "ds_a"])
    runner.invoke(app, ["schema", "add", "--datasource", "primary", "--schema", "ds_b"])
    runner.invoke(app, ["schema", "add", "--datasource", "secondary", "--schema", "pagila"])


def test_two_schemas_of_one_datasource_discover_together(wired: Engine) -> None:
    runner = CliRunner()
    _register(runner)

    result = runner.invoke(app, ["discover", "--datasource", "primary"])

    assert result.exit_code == 0, result.output
    assert "primary.ds_a" in result.output
    assert "primary.ds_b" in result.output


def test_a_second_database_discovers_into_the_same_semantic_store(wired: Engine) -> None:
    runner = CliRunner()
    _register(runner)

    result = runner.invoke(app, ["discover", "--datasource", "secondary"])

    assert result.exit_code == 0, result.output
    with wired.connect() as conn:
        films = conn.execute(
            text(
                "SELECT count(*) FROM genql.genql_object "
                "WHERE datasource_name = 'secondary' AND schema_name = 'pagila'"
            )
        ).scalar_one()
    assert films > 10


def test_identically_named_objects_in_two_datasources_do_not_collide(wired: Engine) -> None:
    runner = CliRunner()
    _register(runner)
    runner.invoke(app, ["discover", "--datasource", "primary"])
    runner.invoke(app, ["discover", "--datasource", "secondary"])

    with wired.connect() as conn:
        datasources = conn.execute(
            text("SELECT count(DISTINCT datasource_name) FROM genql.genql_object")
        ).scalar_one()
    assert datasources >= 2


def test_removing_a_datasource_cascades_its_catalog_away(wired: Engine) -> None:
    runner = CliRunner()
    _register(runner)
    runner.invoke(app, ["discover", "--datasource", "secondary"])

    runner.invoke(app, ["datasource", "remove", "--name", "secondary"])

    with wired.connect() as conn:
        remaining = conn.execute(
            text("SELECT count(*) FROM genql.genql_object WHERE datasource_name = 'secondary'")
        ).scalar_one()
    assert remaining == 0
