from __future__ import annotations

import pytest
from sqlalchemy import Engine, text
from typer.testing import CliRunner

from genql.cli.main import app
from genql.composition_root import Container

FIXTURE = """
DROP SCHEMA IF EXISTS clidemo CASCADE;
CREATE SCHEMA clidemo;
CREATE TABLE clidemo.widget (w_id BIGINT PRIMARY KEY, w_name TEXT);
INSERT INTO clidemo.widget VALUES (1, 'bolt'), (2, 'nut');
"""


@pytest.fixture()
def wired(migrated_engine: Engine, paradedb_dsn: str, monkeypatch) -> Engine:
    with migrated_engine.begin() as conn:
        conn.execute(text(FIXTURE))
        conn.execute(text("DELETE FROM genql.genql_datasource WHERE name = 'clids'"))
    monkeypatch.setenv("GENQL_CLI_DSN", paradedb_dsn)
    monkeypatch.setenv("GENQL_SEMANTIC_DSN", paradedb_dsn)
    Container().reset_singletons()
    return migrated_engine


def test_datasource_add_then_list(wired: Engine) -> None:
    runner = CliRunner()

    added = runner.invoke(
        app,
        [
            "datasource",
            "add",
            "--name",
            "clids",
            "--dialect",
            "postgres",
            "--dsn-env",
            "GENQL_CLI_DSN",
        ],
    )
    listed = runner.invoke(app, ["datasource", "list"])

    assert added.exit_code == 0, added.output
    assert listed.exit_code == 0, listed.output
    assert "clids" in listed.output
    assert "GENQL_CLI_DSN" in listed.output


def test_datasource_add_refuses_a_missing_secret(wired: Engine) -> None:
    result = CliRunner().invoke(
        app,
        [
            "datasource",
            "add",
            "--name",
            "clids",
            "--dialect",
            "postgres",
            "--dsn-env",
            "GENQL_NOT_SET_ANYWHERE",
        ],
    )

    assert result.exit_code == 1
    assert "GENQL_NOT_SET_ANYWHERE" in result.output


def test_schema_add_then_discover_uses_the_registered_scope(wired: Engine) -> None:
    runner = CliRunner()
    runner.invoke(
        app,
        [
            "datasource",
            "add",
            "--name",
            "clids",
            "--dialect",
            "postgres",
            "--dsn-env",
            "GENQL_CLI_DSN",
        ],
    )
    added = runner.invoke(app, ["schema", "add", "--datasource", "clids", "--schema", "clidemo"])
    discovered = runner.invoke(app, ["discover", "--datasource", "clids"])

    assert added.exit_code == 0, added.output
    assert discovered.exit_code == 0, discovered.output
    assert "clids.clidemo" in discovered.output

    with wired.connect() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM genql.genql_object "
                "WHERE datasource_name = 'clids' AND schema_name = 'clidemo'"
            )
        ).scalar_one()
        stamped = conn.execute(
            text(
                "SELECT last_discovered_at IS NOT NULL FROM genql.genql_schema "
                "WHERE datasource_name = 'clids' AND schema_name = 'clidemo'"
            )
        ).scalar_one()
    assert count == 1
    assert stamped is True


def test_schema_add_refuses_a_schema_that_does_not_exist(wired: Engine) -> None:
    runner = CliRunner()
    runner.invoke(
        app,
        [
            "datasource",
            "add",
            "--name",
            "clids",
            "--dialect",
            "postgres",
            "--dsn-env",
            "GENQL_CLI_DSN",
        ],
    )

    result = runner.invoke(
        app, ["schema", "add", "--datasource", "clids", "--schema", "no_such_schema"]
    )

    assert result.exit_code == 1
    assert "no_such_schema" in result.output


def _add(runner: CliRunner) -> None:
    runner.invoke(
        app,
        ["datasource", "add", "--name", "clids", "--dsn-env", "GENQL_CLI_DSN"],
    )


def test_datasource_update_moves_the_endpoint(wired: Engine) -> None:
    runner = CliRunner()
    _add(runner)

    updated = runner.invoke(
        app,
        [
            "datasource",
            "update",
            "--name",
            "clids",
            "--host",
            "new.internal",
            "--port",
            "5433",
            "--database",
            "warehouse",
            "--user",
            "reader",
        ],
    )
    listed = runner.invoke(app, ["datasource", "list"])

    assert updated.exit_code == 0, updated.output
    assert "new.internal:5433/warehouse" in listed.output


def test_datasource_update_can_disable_a_datasource(wired: Engine) -> None:
    runner = CliRunner()
    _add(runner)

    disabled = runner.invoke(app, ["datasource", "update", "--name", "clids", "--disabled"])
    listed = runner.invoke(app, ["datasource", "list", "--enabled-only"])

    assert disabled.exit_code == 0, disabled.output
    assert "clids" not in listed.output


def test_datasource_update_of_an_unknown_name_exits_1(wired: Engine) -> None:
    result = CliRunner().invoke(
        app, ["datasource", "update", "--name", "nope", "--description", "x"]
    )

    assert result.exit_code == 1
    assert "not a registered datasource" in result.output
