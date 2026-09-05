"""A discovery step must report a service failure, not crash the process.

Without this, a warehouse outage escapes DiscoveryRunner.run as a raw
traceback and the halt/resume story is dead code. See final-review.md I2.
"""

from __future__ import annotations

from typing import Any

from genql.discovery.runner import DiscoveryRunner
from genql.discovery.steps.catalog_scan_step import CatalogScanStep
from genql.domain.errors import CatalogAccessError
from genql.domain.ports.discovery_step import DiscoveryContext, StepResult


class _FailingScanService:
    def scan(self, schema: str) -> Any:
        raise CatalogAccessError("warehouse unreachable")


class _RecordingStep:
    name = "next"

    def __init__(self, log: list[str]) -> None:
        self._log = log

    def run(self, ctx: DiscoveryContext) -> StepResult:
        self._log.append(self.name)
        return StepResult(step_name=self.name, succeeded=True, records_written=0, message="ok")


def _ctx() -> DiscoveryContext:
    return DiscoveryContext(schema_name="shop")


def test_a_failing_scan_returns_a_failed_result_instead_of_raising() -> None:
    step = CatalogScanStep(_FailingScanService())  # type: ignore[arg-type]

    result = step.run(_ctx())

    assert result.succeeded is False
    assert result.records_written == 0
    assert "warehouse unreachable" in result.message


def test_runner_halts_after_a_step_catches_a_discovery_error() -> None:
    log: list[str] = []
    runner = DiscoveryRunner(
        [CatalogScanStep(_FailingScanService()), _RecordingStep(log)]  # type: ignore[list-item]
    )

    results = runner.run(_ctx())

    assert log == []  # the second step never ran
    assert results[-1].succeeded is False
