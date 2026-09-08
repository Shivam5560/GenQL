"""Mirrors CatalogScanStep's shape: run() delegates to the service, translates
its typed failure into a failed StepResult, and reports records_written on
success — including the zero-domains case, which succeeds with zero records
rather than failing (Deviation 6)."""

from __future__ import annotations

from genql.discovery.steps.synthetic_ambiguity_log_step import SyntheticAmbiguityLogStep
from genql.domain.errors import AmbiguityExampleGenerationError
from genql.domain.ports.discovery_step import DiscoveryContext


class FakeService:
    def __init__(self, written: int = 0, raises: Exception | None = None) -> None:
        self._written = written
        self._raises = raises

    def generate(self, datasource_name: str) -> int:
        if self._raises:
            raise self._raises
        return self._written


def _ctx() -> DiscoveryContext:
    return DiscoveryContext(datasource_name="local", schema_name="shop")


def test_step_name_is_registered_as_synthetic_ambiguity_log() -> None:
    assert SyntheticAmbiguityLogStep.name == "synthetic_ambiguity_log"


def test_a_successful_run_reports_records_written() -> None:
    result = SyntheticAmbiguityLogStep(FakeService(written=4)).run(_ctx())

    assert result.succeeded is True
    assert result.records_written == 4


def test_zero_domains_succeeds_with_zero_records() -> None:
    result = SyntheticAmbiguityLogStep(FakeService(written=0)).run(_ctx())

    assert result.succeeded is True
    assert result.records_written == 0


def test_a_service_failure_becomes_a_failed_step_result() -> None:
    result = SyntheticAmbiguityLogStep(
        FakeService(raises=AmbiguityExampleGenerationError("boom"))
    ).run(_ctx())

    assert result.succeeded is False
    assert "boom" in result.message
