from __future__ import annotations

from typer.testing import CliRunner

from genql.cli.main import app

runner = CliRunner()


def test_search_command_exists() -> None:
    result = runner.invoke(app, ["semantic", "search", "--help"])

    assert result.exit_code == 0
    assert "top-k" in result.stdout.lower()
