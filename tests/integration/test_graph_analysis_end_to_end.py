"""genql discover, then genql graph analyze, against the real TPC-DS FK
graph on the VM stack — the shape asserted in the spec's Definition of Done
for this phase."""

from __future__ import annotations

import re

from typer.testing import CliRunner

from genql.cli.main import app

runner = CliRunner()

_REPORT_LINE = re.compile(r"(\d+) communities, (\d+) nodes embedded, (\d+) join paths")


def test_discover_then_analyze_produces_communities_embeddings_and_paths() -> None:
    discover_result = runner.invoke(app, ["discover", "--datasource", "local", "--schema", "tpcds"])
    assert discover_result.exit_code == 0

    analyze_result = runner.invoke(app, ["graph", "analyze", "--datasource", "local"])

    assert analyze_result.exit_code == 0
    # Substring checks like `"0 communities" not in stdout` false-fail on any
    # correct count ending in a zero digit (e.g. "10 communities" contains
    # "0 communities"), so parse the actual numbers out and compare them.
    match = _REPORT_LINE.search(analyze_result.stdout)
    assert match is not None, f"unexpected report line: {analyze_result.stdout!r}"
    communities, nodes_embedded, join_paths = (int(group) for group in match.groups())
    assert communities > 0
    assert nodes_embedded > 0
    assert join_paths > 0
