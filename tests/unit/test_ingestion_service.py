"""The pipeline's order is the product, so it is what these tests pin.

Every collaborator is a recording double: the point is not that Leiden runs,
it is that Leiden runs *after* the catalog exists and *after* the graph has
been projected, and that a failure in the middle stops everything downstream
instead of compiling an index from half a warehouse.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from genql.domain.entities.ingestion_job import (
    STEP_SEQUENCE,
    IngestionStep,
    StepStatus,
    pending_steps,
)
from genql.domain.entities.schema_registration import SchemaRegistration
from genql.domain.entities.semantic_overlay import SemanticOverlay
from genql.domain.errors import CompileError, EmptySchemaError
from genql.domain.ports.discovery_step import StepResult
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.domain.value_objects.scope_run_result import ScopeRunResult
from genql.services.datasource.ingestion_service import IngestionService


class StubClock:
    def __init__(self) -> None:
        self._now = datetime(2026, 9, 10, tzinfo=UTC)

    def now(self) -> datetime:
        self._now += timedelta(milliseconds=250)
        return self._now


@dataclass
class Recorder:
    calls: list[str] = field(default_factory=list)


@dataclass
class FakeSchemas:
    recorder: Recorder
    empty: tuple[str, ...] = ()
    registered: list[str] = field(default_factory=list)

    def register(self, ref: SchemaRef, _description: str | None) -> SchemaRegistration:
        if ref.schema_name in self.empty:
            raise EmptySchemaError(ref.qualified_name)
        self.recorder.calls.append(f"register:{ref.schema_name}")
        self.registered.append(ref.schema_name)
        return SchemaRegistration(datasource_name=ref.datasource_name, schema_name=ref.schema_name)

    def list_for_datasource(self, datasource_name: str) -> list[SchemaRegistration]:
        return [
            SchemaRegistration(datasource_name=datasource_name, schema_name=name)
            for name in self.registered
        ]


@dataclass
class FakeDiscovery:
    recorder: Recorder
    failing: tuple[str, ...] = ()

    def run_scope(self, scope, sample_limit, start_from=None):  # type: ignore[no-untyped-def]
        self.recorder.calls.append(f"discover:{','.join(scope.schema_names)}")
        return [
            ScopeRunResult(
                ref=ref,
                results=(
                    StepResult(
                        step_name="catalog_scan",
                        succeeded=ref.schema_name not in self.failing,
                        records_written=11,
                        message="scanned",
                    ),
                ),
            )
            for ref in scope.refs()
        ]


@dataclass
class FakeOverlays:
    overlay: SemanticOverlay | None = None

    def load(self, _datasource_name: str) -> SemanticOverlay | None:
        return self.overlay


@dataclass
class FakeReportService:
    recorder: Recorder
    label: str
    report: object
    raises: Exception | None = None

    def _call(self, *_args: object, **_kwargs: object) -> object:
        self.recorder.calls.append(self.label)
        if self.raises is not None:
            raise self.raises
        return self.report

    apply = compile = analyze = discover = _call


class OverlayReport:
    objects_updated = 2
    columns_updated = 3
    metrics_written = 1
    rules_written = 0
    join_hints_written = 1


class CompileReport:
    documents = 41
    comments_written = 0


class GraphReport:
    communities = 5
    embedded_nodes = 41
    join_paths = 12


class DomainReport:
    domains = 4
    members = 41


def build(
    recorder: Recorder,
    *,
    empty: tuple[str, ...] = (),
    overlay: SemanticOverlay | None = None,
    compile_raises: Exception | None = None,
    discovery_failing: tuple[str, ...] = (),
) -> IngestionService:
    return IngestionService(
        schemas=FakeSchemas(recorder, empty=empty),  # type: ignore[arg-type]
        discovery=FakeDiscovery(recorder, failing=discovery_failing),
        overlays=FakeOverlays(overlay),
        overlay_service=FakeReportService(recorder, "overlay", OverlayReport()),  # type: ignore[arg-type]
        compiler=FakeReportService(recorder, "compile", CompileReport(), compile_raises),  # type: ignore[arg-type]
        graph=FakeReportService(recorder, "graph", GraphReport()),  # type: ignore[arg-type]
        domains=FakeReportService(recorder, "domains", DomainReport()),  # type: ignore[arg-type]
        clock=StubClock(),
        sample_limit=5,
    )


def run(service: IngestionService, schemas: tuple[str, ...] = ("shop",)) -> list[IngestionStep]:
    seen: list[IngestionStep] = []
    service.run("warehouse", schemas, pending_steps(), seen.append)
    return seen


def test_the_stages_run_in_the_one_order_that_works() -> None:
    recorder = Recorder()

    run(build(recorder, overlay=SemanticOverlay(datasource="warehouse")))

    assert recorder.calls == [
        "register:shop",
        "discover:shop",
        "overlay",
        "compile",
        "graph",
        "domains",
    ]


def test_every_step_is_reported_running_before_it_is_reported_done() -> None:
    seen = run(build(Recorder()))

    running = [s.name for s in seen if s.status is StepStatus.RUNNING]
    assert running == list(STEP_SEQUENCE)
    # A client watching the stream learns a stage started before it finishes,
    # which is the entire reason the stream exists.
    for name in STEP_SEQUENCE:
        indices = [i for i, s in enumerate(seen) if s.name == name]
        assert seen[indices[0]].status is StepStatus.RUNNING


def test_a_datasource_with_no_overlay_file_skips_that_step_rather_than_failing() -> None:
    seen = run(build(Recorder()))

    overlay = [s for s in seen if s.name == "semantic_overlay"][-1]
    assert overlay.status is StepStatus.SKIPPED
    assert overlay.detail == "no overlay file for this datasource"


def test_one_unreadable_schema_is_skipped_while_the_rest_are_registered() -> None:
    recorder = Recorder()

    seen = run(build(recorder, empty=("archive",)), schemas=("shop", "archive"))

    step = [s for s in seen if s.name == "schema_registration"][-1]
    assert step.status is StepStatus.SUCCEEDED
    assert step.records_written == 1
    assert "skipped archive" in (step.detail or "")


def test_a_datasource_with_no_readable_schema_at_all_is_refused() -> None:
    service = build(Recorder(), empty=("shop",))

    with pytest.raises(EmptySchemaError):
        run(service)


def test_a_failing_stage_stops_the_pipeline_and_marks_only_that_step_failed() -> None:
    recorder = Recorder()
    service = build(recorder, compile_raises=CompileError("index build blew up"))
    seen: list[IngestionStep] = []

    with pytest.raises(CompileError):
        service.run("warehouse", ("shop",), pending_steps(), seen.append)

    # Nothing downstream of the failure ran.
    assert "graph" not in recorder.calls
    assert "domains" not in recorder.calls
    failed = [s for s in seen if s.status is StepStatus.FAILED]
    assert [s.name for s in failed] == ["semantic_compile"]
    assert failed[0].detail == "CompileError: index build blew up"


def test_a_resumed_run_executes_only_the_steps_it_was_given() -> None:
    recorder = Recorder()

    build(recorder).run(
        "warehouse", ("shop",), pending_steps(start_from="semantic_compile"), lambda _s: None
    )

    assert recorder.calls == ["compile", "graph", "domains"]


def test_each_finished_step_carries_how_long_it_took() -> None:
    seen = run(build(Recorder()))

    finished = [s for s in seen if s.status is not StepStatus.RUNNING]
    assert all(s.duration_ms > 0 for s in finished)
