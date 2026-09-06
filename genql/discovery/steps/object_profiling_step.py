"""Sequenced after graph_projection: it needs nothing from the graph, but
running last among the per-schema steps means a profiling failure never
blocks Phase 3's steps from completing for that schema. Text embedding is
folded into ObjectProfilingService itself rather than a separate step —
splitting it out would mean re-reading a just-written description from
Postgres a moment after writing it, for no benefit."""

from __future__ import annotations

from typing import ClassVar

from genql.discovery.registry import DISCOVERY_STEPS
from genql.domain.errors import DiscoveryError
from genql.domain.ports.discovery_step import DiscoveryContext, StepResult
from genql.services.semantic.object_profiling_service import ObjectProfilingService


@DISCOVERY_STEPS.register("object_profiling")
class ObjectProfilingStep:
    name: ClassVar[str] = "object_profiling"

    def __init__(self, service: ObjectProfilingService) -> None:
        self._service = service

    def run(self, ctx: DiscoveryContext) -> StepResult:
        try:
            report = self._service.profile(ctx.ref, ctx.sample_limit)
        except DiscoveryError as exc:
            return StepResult(
                step_name=self.name, succeeded=False, records_written=0, message=str(exc)
            )
        return StepResult(
            step_name=self.name,
            succeeded=True,
            records_written=report.objects_profiled,
            message=(
                f"{report.objects_profiled} objects profiled, {report.columns_profiled} columns"
            ),
        )
