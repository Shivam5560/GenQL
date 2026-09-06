"""Step: project one schema's objects and FK edges into Neo4j.

Sequenced immediately after catalog_scan at the composition root — it needs
that schema's objects and constraints already committed to Postgres, and
gains nothing from waiting for data_profiling.
"""

from __future__ import annotations

from typing import ClassVar

from genql.discovery.registry import DISCOVERY_STEPS
from genql.domain.errors import DiscoveryError
from genql.domain.ports.discovery_step import DiscoveryContext, StepResult
from genql.services.graph.graph_projection_service import GraphProjectionService


@DISCOVERY_STEPS.register("graph_projection")
class GraphProjectionStep:
    name: ClassVar[str] = "graph_projection"

    def __init__(self, service: GraphProjectionService) -> None:
        self._service = service

    def run(self, ctx: DiscoveryContext) -> StepResult:
        try:
            report = self._service.project(ctx.ref)
        except DiscoveryError as exc:
            return StepResult(
                step_name=self.name, succeeded=False, records_written=0, message=str(exc)
            )
        return StepResult(
            step_name=self.name,
            succeeded=True,
            records_written=report.total,
            message=f"{report.objects} objects, {report.edges} edges",
        )
