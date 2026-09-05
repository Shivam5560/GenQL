"""Step 2 of the discovery pipeline: sample real values per column."""

from __future__ import annotations

from typing import ClassVar

from genql.discovery.registry import DISCOVERY_STEPS
from genql.domain.errors import DiscoveryError
from genql.domain.ports.discovery_step import DiscoveryContext, StepResult
from genql.services.discovery.profiling_service import ProfilingService


@DISCOVERY_STEPS.register("data_profiling")
class DataProfilingStep:
    name: ClassVar[str] = "data_profiling"

    def __init__(self, service: ProfilingService) -> None:
        self._service = service

    def run(self, ctx: DiscoveryContext) -> StepResult:
        try:
            written = self._service.profile(ctx.ref, ctx.sample_limit)
        except DiscoveryError as exc:
            return StepResult(
                step_name=self.name,
                succeeded=False,
                records_written=0,
                message=str(exc),
            )
        skipped = self._service.skipped
        return StepResult(
            step_name=self.name,
            succeeded=True,
            records_written=written,
            message=f"{written} columns profiled, {len(skipped)} skipped",
        )
