"""Writes evaluation reports as JSON.

JSON rather than the printed table because the table is for a person reading
one run and this is for comparing runs over time — and because a Pydantic
model already serializes itself correctly, including the computed accuracy.
"""

from __future__ import annotations

import json
from pathlib import Path

from genql.domain.entities.golden_run_report import GoldenRunReport
from genql.domain.errors import EvaluationError


class JsonReportWriter:
    def write(self, path: str, reports: tuple[GoldenRunReport, ...]) -> None:
        payload = [
            {
                "ablation": report.ablation_name,
                "accuracy": report.accuracy,
                "passed": report.passed_count,
                "total": len(report.outcomes),
                "outcomes": [outcome.model_dump() for outcome in report.outcomes],
            }
            for report in reports
        ]
        try:
            Path(path).write_text(json.dumps(payload, indent=2, default=str))
        except OSError as exc:
            raise EvaluationError(f"could not write the report to {path}: {exc}") from exc
