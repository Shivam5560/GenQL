"""No semantic/<datasource>.yaml present is a no-op, not an error — not
every datasource needs authored overrides."""

from __future__ import annotations

from typer.testing import CliRunner

from genql.cli.main import app

runner = CliRunner()


def test_overlay_with_no_file_present_is_a_clean_no_op(tmp_path: object) -> None:
    result = runner.invoke(app, ["semantic", "overlay", "--datasource", "nonexistent_ds_xyz"])

    assert result.exit_code == 0
    assert "no overlay file" in result.stdout.lower()
