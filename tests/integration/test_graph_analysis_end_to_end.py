"""genql discover, then genql graph analyze, against the real TPC-DS FK
graph on the VM stack — the shape asserted in the spec's Definition of Done
for this phase."""

from __future__ import annotations

from typer.testing import CliRunner

from genql.cli.main import app

runner = CliRunner()


def test_discover_then_analyze_produces_communities_embeddings_and_paths() -> None:
    discover_result = runner.invoke(app, ["discover", "--datasource", "local", "--schema", "tpcds"])
    assert discover_result.exit_code == 0

    analyze_result = runner.invoke(app, ["graph", "analyze", "--datasource", "local"])

    assert analyze_result.exit_code == 0
    assert "0 communities" not in analyze_result.stdout
    assert "0 nodes embedded" not in analyze_result.stdout
    assert "0 join paths" not in analyze_result.stdout
