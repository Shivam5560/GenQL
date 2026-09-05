from __future__ import annotations

import pytest

from genql.discovery.runner import DiscoveryRunner
from genql.domain.errors import UnknownDiscoveryStepError
from genql.domain.ports.discovery_step import DiscoveryContext, StepResult


class RecordingStep:
    def __init__(self, name: str, log: list[str], fail: bool = False) -> None:
        self.name = name
        self._log = log
        self._fail = fail

    def run(self, ctx: DiscoveryContext) -> StepResult:
        self._log.append(self.name)
        if self._fail:
            return StepResult(
                step_name=self.name, succeeded=False, records_written=0, message="boom"
            )
        return StepResult(step_name=self.name, succeeded=True, records_written=1, message="ok")


def _ctx() -> DiscoveryContext:
    return DiscoveryContext(schema_name="shop", sample_limit=5)


def test_steps_run_in_order() -> None:
    log: list[str] = []
    runner = DiscoveryRunner([RecordingStep("a", log), RecordingStep("b", log)])
    results = runner.run(_ctx())
    assert log == ["a", "b"]
    assert [r.step_name for r in results] == ["a", "b"]


def test_run_halts_on_first_failure() -> None:
    log: list[str] = []
    runner = DiscoveryRunner(
        [RecordingStep("a", log), RecordingStep("b", log, fail=True), RecordingStep("c", log)]
    )
    results = runner.run(_ctx())
    assert log == ["a", "b"]
    assert results[-1].succeeded is False


def test_start_from_skips_earlier_steps() -> None:
    log: list[str] = []
    runner = DiscoveryRunner(
        [RecordingStep("a", log), RecordingStep("b", log), RecordingStep("c", log)]
    )
    runner.run(_ctx(), start_from="b")
    assert log == ["b", "c"]


def test_start_from_an_unknown_step_raises_a_typed_error_naming_the_options() -> None:
    runner = DiscoveryRunner([RecordingStep("a", []), RecordingStep("b", [])])

    with pytest.raises(UnknownDiscoveryStepError) as excinfo:
        runner.run(_ctx(), start_from="typo")

    assert "typo" in str(excinfo.value)
    assert "a" in str(excinfo.value)
    assert "b" in str(excinfo.value)
