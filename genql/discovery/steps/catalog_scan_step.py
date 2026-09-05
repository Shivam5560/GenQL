"""Step 1 of the discovery pipeline: scan the warehouse catalog."""

from __future__ import annotations

from typing import ClassVar

from genql.discovery.registry import DISCOVERY_STEPS
from genql.domain.errors import DiscoveryError
from genql.domain.ports.discovery_step import DiscoveryContext, StepResult
from genql.services.discovery.catalog_scan_service import CatalogScanService


@DISCOVERY_STEPS.register("catalog_scan")
class CatalogScanStep:
    name: ClassVar[str] = "catalog_scan"

    def __init__(self, service: CatalogScanService) -> None:
        self._service = service

    def run(self, ctx: DiscoveryContext) -> StepResult:
        try:
            report = self._service.scan(ctx.schema_name)
        except DiscoveryError as exc:
            return StepResult(
                step_name=self.name,
                succeeded=False,
                records_written=0,
                message=str(exc),
            )
        ctx.artifacts["catalog_scan"] = report
        return StepResult(
            step_name=self.name,
            succeeded=True,
            records_written=report.total,
            message=(
                f"{report.objects} objects, {report.columns} columns, "
                f"{report.constraints} constraints"
            ),
        )
