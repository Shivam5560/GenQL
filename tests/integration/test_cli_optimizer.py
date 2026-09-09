"""The command's two outputs: a ranked table, and the empty-state line that
tells the operator why there is nothing to show. The empty state is the one a
fresh installation always hits, so it is the one worth a test."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import Engine
from typer.testing import CliRunner

from genql.cli.main import app
from genql.composition_root import Container

pytestmark = pytest.mark.integration

runner = CliRunner()


@pytest.fixture()
def wired(
    migrated_engine: Engine,
    paradedb_dsn: str,
    monkeypatch: pytest.MonkeyPatch,
    register_schema: Callable[[str, str], None],
) -> Engine:
    # `local` must exist for the happy path and must NOT be invented for the
    # unknown-name path — the whole point of the second test is that an
    # unregistered name is refused rather than reported empty.
    register_schema("local", "tpcds")
    monkeypatch.setenv("GENQL_WAREHOUSE_DSN", paradedb_dsn)
    monkeypatch.setenv("GENQL_SEMANTIC_DSN", paradedb_dsn)
    Container().reset_singletons()
    return migrated_engine


def test_recommend_indexes_on_a_fresh_store_explains_why_it_is_empty(wired: Engine) -> None:
    result = runner.invoke(app, ["optimizer", "recommend-indexes", "--datasource", "local"])

    assert result.exit_code == 0, result.output
    assert "no recommendations yet" in result.stdout


def test_recommend_indexes_on_an_unknown_datasource_exits_nonzero(wired: Engine) -> None:
    result = runner.invoke(app, ["optimizer", "recommend-indexes", "--datasource", "nope"])

    assert result.exit_code == 1
