"""End-to-end through the CLI: discover, then analyze, against the VM stack."""

from __future__ import annotations

import os

from typer.testing import CliRunner

from genql.cli.main import app

runner = CliRunner()


def test_graph_analyze_reports_at_least_one_community(monkeypatch: object) -> None:
    result = runner.invoke(app, ["discover", "--datasource", "local", "--schema", "tpcds"])
    assert result.exit_code == 0

    result = runner.invoke(app, ["graph", "analyze", "--datasource", "local"])

    assert result.exit_code == 0
    assert "communities" in result.stdout


def test_graph_rebuild_does_not_touch_the_warehouse(monkeypatch: object) -> None:
    """Rebuild reads only from Postgres — breaking GENQL_WAREHOUSE_DSN must
    not affect it."""
    original = os.environ.pop("GENQL_WAREHOUSE_DSN", None)
    try:
        result = runner.invoke(app, ["graph", "rebuild", "--datasource", "local"])
        assert result.exit_code == 0
    finally:
        if original is not None:
            os.environ["GENQL_WAREHOUSE_DSN"] = original
