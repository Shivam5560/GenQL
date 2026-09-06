"""Needs graph analyze (structural embeddings) and discover with
object_profiling (text embeddings) to have already run — see Task 12 for the
full ordered chain. This test only checks the command exists and reports a
sane shape; it is expected to fail with a clear domain error, not a crash,
if run in isolation without those prerequisites."""

from __future__ import annotations

from typer.testing import CliRunner

from genql.cli.main import app

runner = CliRunner()


def test_graph_domains_command_exists() -> None:
    result = runner.invoke(app, ["graph", "domains", "--help"])

    assert result.exit_code == 0
    assert "datasource" in result.stdout.lower()
