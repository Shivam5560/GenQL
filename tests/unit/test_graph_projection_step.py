"""The step delegates to the service and reports a typed result, same shape
as CatalogScanStep."""

from __future__ import annotations

from genql.discovery.steps.graph_projection_step import GraphProjectionStep
from genql.domain.ports.discovery_step import DiscoveryContext
from genql.services.graph.graph_projection_service import GraphProjectionReport


class FakeGraphProjectionService:
    def __init__(self, report: GraphProjectionReport) -> None:
        self._report = report
        self.seen_refs: list[str] = []

    def project(self, ref: object) -> GraphProjectionReport:
        self.seen_refs.append(ref.qualified_name)  # type: ignore[attr-defined]
        return self._report


def test_step_reports_success_and_records_written() -> None:
    service = FakeGraphProjectionService(GraphProjectionReport(objects=3, edges=2))
    step = GraphProjectionStep(service)  # type: ignore[arg-type]
    ctx = DiscoveryContext(datasource_name="local", schema_name="shop")

    result = step.run(ctx)

    assert result.succeeded is True
    assert result.records_written == 5
    assert service.seen_refs == ["local.shop"]


def test_step_name_is_graph_projection() -> None:
    assert GraphProjectionStep.name == "graph_projection"
