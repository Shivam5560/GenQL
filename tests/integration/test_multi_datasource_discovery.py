"""n schemas across n databases, shown rather than asserted.

Requires GENQL_WH2_DSN to point at the genql_wh2 database seeded with Pagila
(see data/README.md). Skipped when it is unset, so the suite still runs on a
machine that has only the primary warehouse.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, text
from typer.testing import CliRunner

from genql.cli.main import app
from genql.composition_root import Container
from genql.infrastructure.db.engine import create_engine_from_dsn

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

# Deliberately the SAME schema and table name as the primary warehouse's
# ds_a.alpha above, in a DIFFERENT database. Without datasource_name in the
# identity these two rows are one row, so this is the fixture that makes the
# collision test capable of failing.
WH2_FIXTURE = """
DROP SCHEMA IF EXISTS ds_a CASCADE;
CREATE SCHEMA ds_a;
CREATE TABLE ds_a.alpha (wh2_id BIGINT PRIMARY KEY, wh2_label TEXT);
INSERT INTO ds_a.alpha VALUES (1, 'elsewhere');
"""


@pytest.fixture()
def wh2_engine() -> Iterator[Engine]:
    engine = create_engine_from_dsn(WH2_DSN)
    with engine.begin() as conn:
        conn.execute(text(WH2_FIXTURE))
    yield engine
    engine.dispose()


@pytest.fixture()
def wired(migrated_engine: Engine, wh2_engine: Engine, paradedb_dsn: str, monkeypatch) -> Engine:
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


def _invoke(runner: CliRunner, args: list[str]) -> None:
    """Every registration must succeed. A silently failed `datasource add`
    would otherwise surface only as a puzzling assertion about missing rows
    three calls later."""
    result = runner.invoke(app, args)
    assert result.exit_code == 0, f"{' '.join(args)} failed: {result.output}"


def _register(runner: CliRunner) -> None:
    _invoke(
        runner,
        ["datasource", "add", "--name", "primary", "--dialect", "postgres"]
        + ["--dsn-env", "GENQL_PRIMARY_DSN"],
    )
    _invoke(
        runner,
        ["datasource", "add", "--name", "secondary", "--dialect", "postgres"]
        + ["--dsn-env", "GENQL_SECONDARY_DSN"],
    )
    _invoke(runner, ["schema", "add", "--datasource", "primary", "--schema", "ds_a"])
    _invoke(runner, ["schema", "add", "--datasource", "primary", "--schema", "ds_b"])
    _invoke(runner, ["schema", "add", "--datasource", "secondary", "--schema", "ds_a"])
    _invoke(runner, ["schema", "add", "--datasource", "secondary", "--schema", "pagila"])


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
    """`ds_a.alpha` exists in both warehouses. Both rows must survive, told
    apart by datasource_name — a count of distinct datasources would pass on
    leftovers from any other test in this shared semantic store, so pin the
    assertion to the colliding name itself."""
    runner = CliRunner()
    _register(runner)
    _invoke(runner, ["discover", "--datasource", "primary"])
    _invoke(runner, ["discover", "--datasource", "secondary"])

    with wired.connect() as conn:
        owners = conn.execute(
            text(
                "SELECT datasource_name FROM genql.genql_object "
                "WHERE schema_name = 'ds_a' AND object_name = 'alpha' "
                "ORDER BY datasource_name"
            )
        ).scalars()
        columns = conn.execute(
            text(
                "SELECT datasource_name, column_name FROM genql.genql_column "
                "WHERE schema_name = 'ds_a' AND object_name = 'alpha' "
                "AND column_name IN ('a_id', 'wh2_id')"
            )
        ).all()

    assert list(owners) == ["primary", "secondary"]
    # Same qualified name, different shape: proof the two rows are the two
    # real tables and not one row overwritten by the second scan.
    assert sorted(columns) == [("primary", "a_id"), ("secondary", "wh2_id")]


def test_removing_a_datasource_cascades_its_catalog_away(wired: Engine) -> None:
    runner = CliRunner()
    _register(runner)
    _invoke(runner, ["discover", "--datasource", "secondary"])

    with wired.connect() as conn:
        # Assert the rows were there first: without this the cascade assertion
        # below passes just as well when discovery silently wrote nothing.
        discovered = conn.execute(
            text("SELECT count(*) FROM genql.genql_object WHERE datasource_name = 'secondary'")
        ).scalar_one()
    assert discovered > 0

    _invoke(runner, ["datasource", "remove", "--name", "secondary"])

    with wired.connect() as conn:
        remaining = conn.execute(
            text("SELECT count(*) FROM genql.genql_object WHERE datasource_name = 'secondary'")
        ).scalar_one()
    assert remaining == 0
