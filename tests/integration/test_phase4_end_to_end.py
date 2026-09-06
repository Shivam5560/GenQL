"""genql discover -> graph analyze -> graph domains -> semantic overlay ->
semantic compile -> semantic search against local.tpcds. Skipped cleanly
without an OpenRouter key — nearly every step here needs one."""

from __future__ import annotations

import os

import pytest
from typer.testing import CliRunner

from genql.cli.main import app

pytestmark = pytest.mark.skipif(
    not os.environ.get("GENQL_OPENROUTER_API_KEY"), reason="GENQL_OPENROUTER_API_KEY not set"
)

runner = CliRunner()


def test_full_chain_answers_a_tpcds_question() -> None:
    discover = runner.invoke(app, ["discover", "--datasource", "local", "--schema", "tpcds"])
    assert discover.exit_code == 0, discover.stdout

    analyze = runner.invoke(app, ["graph", "analyze", "--datasource", "local"])
    assert analyze.exit_code == 0, analyze.stdout

    domains = runner.invoke(app, ["graph", "domains", "--datasource", "local"])
    assert domains.exit_code == 0, domains.stdout
    assert "0 domains" not in domains.stdout

    overlay = runner.invoke(app, ["semantic", "overlay", "--datasource", "local"])
    assert overlay.exit_code == 0, overlay.stdout

    compile_result = runner.invoke(app, ["semantic", "compile", "--datasource", "local"])
    assert compile_result.exit_code == 0, compile_result.stdout
    assert "0 documents" not in compile_result.stdout

    search = runner.invoke(
        app, ["semantic", "search", "--datasource", "local", "total sales by store"]
    )
    assert search.exit_code == 0, search.stdout
    assert search.stdout.strip() != ""
