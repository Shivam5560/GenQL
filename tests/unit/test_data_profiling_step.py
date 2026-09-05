"""A discovery step must report a service failure, not crash the process.

Mirrors test_catalog_scan_step.py for the profiling step. See final-review.md I2.
"""

from __future__ import annotations

from genql.discovery.steps.data_profiling_step import DataProfilingStep
from genql.domain.errors import ProfilingError
from genql.domain.ports.discovery_step import DiscoveryContext
from genql.domain.value_objects.schema_ref import SchemaRef


class _FailingProfilingService:
    skipped: list[str] = []

    def profile(self, ref: SchemaRef, sample_limit: int) -> int:
        raise ProfilingError("shop.customer.c_state", "connection refused")


def test_a_failing_profile_run_returns_a_failed_result_instead_of_raising() -> None:
    step = DataProfilingStep(_FailingProfilingService())  # type: ignore[arg-type]

    result = step.run(DiscoveryContext(datasource_name="local", schema_name="shop"))

    assert result.succeeded is False
    assert result.records_written == 0
    assert "connection refused" in result.message
