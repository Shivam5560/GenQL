from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import Engine, text
from typer.testing import CliRunner

from genql.cli.main import app
from genql.composition_root import Container

FIXTURE = """
DROP SCHEMA IF EXISTS e2e CASCADE;
CREATE SCHEMA e2e;
CREATE TABLE e2e.region (r_id BIGINT PRIMARY KEY, r_name TEXT);
INSERT INTO e2e.region VALUES (1, 'West'), (2, 'East'), (3, 'North');
"""


@pytest.fixture()
def wired(
    migrated_engine: Engine,
    paradedb_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
    register_schema: Callable[[str, str], None],
) -> Engine:
    with migrated_engine.begin() as conn:
        conn.execute(text(FIXTURE))
    register_schema("local", "e2e")
    monkeypatch.setenv("GENQL_WAREHOUSE_DSN", paradedb_dsn)
    monkeypatch.setenv("GENQL_SEMANTIC_DSN", paradedb_dsn)
    # DeclarativeContainer deep-copies its providers on every instantiation, so
    # this clears the singletons of this throwaway instance only — it is a
    # no-op for the fresh Container() each command builds, kept because every
    # Container() in these tests is already fresh and nothing here depends on
    # cross-instance state. Do not read it as global test isolation.
    Container().reset_singletons()
    return migrated_engine


def test_discover_scans_and_profiles(wired: Engine) -> None:
    result = CliRunner().invoke(app, ["discover", "--datasource", "local", "--schema", "e2e"])

    assert result.exit_code == 0, result.output
    assert "local.e2e" in result.output
    assert "ok   catalog_scan" in result.output
    assert "ok   data_profiling" in result.output

    with wired.connect() as conn:
        samples = conn.execute(
            text(
                "SELECT sample_values FROM genql.genql_column_profile "
                "WHERE object_name = 'region' AND column_name = 'r_name'"
            )
        ).scalar_one()
    assert set(samples) == {"West", "East", "North"}


def test_steps_lists_the_registry() -> None:
    result = CliRunner().invoke(app, ["steps"])
    assert result.exit_code == 0
    assert result.output.split() == ["catalog_scan", "data_profiling"]
