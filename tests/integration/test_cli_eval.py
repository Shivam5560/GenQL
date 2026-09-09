"""The two commands' output contracts. Counts beside every accuracy is not
cosmetic: a report showing 0.83 without 5/6 invites a reader to treat six
cases as a measurement."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from genql.cli.main import app

pytestmark = [pytest.mark.integration, pytest.mark.real_provider]

runner = CliRunner()


def test_golden_prints_accuracy_with_its_counts() -> None:
    result = runner.invoke(app, ["eval", "golden", "--datasource", "local"])

    assert result.exit_code == 0
    assert "/" in result.stdout  # e.g. "accuracy: 0.83 (5/6)"
    assert "accuracy" in result.stdout.lower()


def test_golden_writes_a_json_report_when_asked(tmp_path: Path) -> None:
    report = tmp_path / "report.json"

    result = runner.invoke(
        app, ["eval", "golden", "--datasource", "local", "--report", str(report)]
    )

    assert result.exit_code == 0
    payload = json.loads(report.read_text())
    assert payload[0]["ablation"] == "full"
    assert "outcomes" in payload[0]


def test_ablate_names_the_layer_it_cannot_measure() -> None:
    result = runner.invoke(app, ["eval", "ablate", "--datasource", "local", "--ablation", "full"])

    assert result.exit_code == 0
    assert "query log" in result.stdout


def test_ablate_reports_each_ablations_delta_from_the_baseline() -> None:
    result = runner.invoke(
        app,
        [
            "eval",
            "ablate",
            "--datasource",
            "local",
            "--ablation",
            "full",
            "--ablation",
            "no_domains",
        ],
    )

    assert result.exit_code == 0
    assert "delta" in result.stdout.lower()


def test_an_unknown_ablation_exits_nonzero_and_lists_the_real_ones() -> None:
    result = runner.invoke(
        app, ["eval", "ablate", "--datasource", "local", "--ablation", "invented"]
    )

    assert result.exit_code == 1
    assert "no_domains" in result.stdout
