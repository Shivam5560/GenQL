"""The layering is enforced mechanically, so it is tested mechanically."""

from __future__ import annotations

import subprocess


def test_import_contracts_hold() -> None:
    result = subprocess.run(
        ["uv", "run", "lint-imports"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_file_length_gate_rejects_a_long_file(tmp_path) -> None:
    offender = tmp_path / "too_long.py"
    offender.write_text("x = 1\n" * 300, encoding="utf-8")
    result = subprocess.run(
        ["python", "scripts/check_file_length.py", str(offender)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    assert "limit 250" in result.stderr
