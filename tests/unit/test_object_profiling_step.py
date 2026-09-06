from __future__ import annotations

from genql.discovery.steps.object_profiling_step import ObjectProfilingStep
from genql.domain.ports.discovery_step import DiscoveryContext
from genql.services.semantic.object_profiling_service import ObjectProfilingReport


class FakeService:
    def profile(self, ref: object, sample_limit: int) -> ObjectProfilingReport:
        return ObjectProfilingReport(objects_profiled=2, columns_profiled=9)


def test_run_reports_objects_and_columns_profiled() -> None:
    step = ObjectProfilingStep(FakeService())
    ctx = DiscoveryContext(datasource_name="local", schema_name="shop", sample_limit=5)

    result = step.run(ctx)

    assert result.succeeded
    assert result.records_written == 2
    assert "9 columns" in result.message
