"""Submitting a job is a request; running it is not.

These pin the three things a client depends on: registration failures surface
immediately rather than inside a job, a second job for a datasource already
being ingested is refused, and a resumed run keeps the earlier steps' results
visible instead of blanking them back to pending.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from genql.domain.entities.datasource import Datasource
from genql.domain.entities.ingestion_job import (
    IngestionJob,
    IngestionStep,
    JobStatus,
    StepStatus,
)
from genql.domain.errors import (
    IngestionInProgressError,
    MissingDatasourceSecretError,
    NoIngestionJobError,
    UnknownDatasourceError,
    UnknownIngestionStepError,
)
from genql.domain.value_objects.datasource_connection import DatasourceConnection
from genql.services.datasource.onboarding_service import OnboardingService


class StubClock:
    def __init__(self) -> None:
        self._now = datetime(2026, 9, 10, tzinfo=UTC)

    def now(self) -> datetime:
        self._now += timedelta(seconds=1)
        return self._now


CONNECTION = DatasourceConnection(
    host="warehouse.internal", port=5432, database="analytics", username="reader", password="p"
)


class FakeDatasourceService:
    def __init__(self, raises: Exception | None = None) -> None:
        self.raises = raises
        self.registered: list[str] = []

    def register(
        self, name: str, dialect: str, connection: DatasourceConnection, description: str | None
    ) -> Datasource:
        if self.raises is not None:
            raise self.raises
        self.registered.append(name)
        return Datasource(
            name=name,
            dialect=dialect,
            host=connection.host,
            port=connection.port,
            database=connection.database,
            username=connection.username,
            description=description,
        )


class FakeDatasourceRepository:
    def __init__(self, known: tuple[str, ...] = ("warehouse",)) -> None:
        self.known = known

    def get(self, name: str) -> Datasource:
        if name not in self.known:
            raise UnknownDatasourceError(name, list(self.known))
        return Datasource(name=name, dialect="postgres", dsn_env_var="DSN")


class FakeJobs:
    def __init__(self) -> None:
        self.submitted: list[IngestionJob] = []
        self.latest: IngestionJob | None = None
        self.active: IngestionJob | None = None

    def submit(self, job: IngestionJob) -> None:
        self.submitted.append(job)

    def latest_for_datasource(self, _name: str) -> IngestionJob | None:
        return self.latest

    def active_for_datasource(self, _name: str) -> IngestionJob | None:
        return self.active


def build(
    jobs: FakeJobs | None = None, datasources: FakeDatasourceService | None = None
) -> tuple[OnboardingService, FakeJobs]:
    store = jobs or FakeJobs()
    service = OnboardingService(
        datasources=datasources or FakeDatasourceService(),  # type: ignore[arg-type]
        datasource_repository=FakeDatasourceRepository(),  # type: ignore[arg-type]
        jobs=store,  # type: ignore[arg-type]
        clock=StubClock(),
    )
    return service, store


def finished_job(datasource: str = "warehouse") -> IngestionJob:
    return IngestionJob(
        job_id="old",
        datasource_name=datasource,
        user_id="u-1",
        status=JobStatus.SUCCEEDED,
        schemas=("shop", "billing"),
        steps=(
            IngestionStep(
                name="schema_registration",
                status=StepStatus.SUCCEEDED,
                detail="2 schema(s) registered",
                records_written=2,
            ),
            IngestionStep(
                name="discovery", status=StepStatus.SUCCEEDED, detail="2/2 schemas discovered"
            ),
            IngestionStep(name="semantic_overlay", status=StepStatus.SKIPPED),
            IngestionStep(name="semantic_compile", status=StepStatus.FAILED),
            IngestionStep(name="graph_analysis"),
            IngestionStep(name="domain_discovery"),
        ),
        created_at=datetime(2026, 9, 9, tzinfo=UTC),
    )


def test_registering_queues_a_job_and_returns_before_any_stage_runs() -> None:
    service, jobs = build()

    datasource, job = service.register_and_submit(
        "warehouse", "postgres", CONNECTION, None, ["shop"], "u-1"
    )

    assert datasource.name == "warehouse"
    assert job.status is JobStatus.QUEUED
    assert job.schemas == ("shop",)
    assert [s.status for s in job.steps] == [StepStatus.PENDING] * 6
    assert jobs.submitted == [job]


def test_an_unset_dsn_variable_fails_the_request_rather_than_the_job() -> None:
    service, jobs = build(
        datasources=FakeDatasourceService(MissingDatasourceSecretError("warehouse", "DSN"))
    )

    with pytest.raises(MissingDatasourceSecretError):
        service.register_and_submit("warehouse", "postgres", CONNECTION, None, [], "u-1")

    assert jobs.submitted == []


def test_a_second_job_for_a_datasource_already_ingesting_is_refused() -> None:
    jobs = FakeJobs()
    jobs.active = finished_job().model_copy(update={"status": JobStatus.RUNNING, "job_id": "live"})
    service, _ = build(jobs)

    with pytest.raises(IngestionInProgressError) as caught:
        service.register_and_submit("warehouse", "postgres", CONNECTION, None, [], "u-1")

    assert caught.value.job_id == "live"


def test_a_retry_reuses_the_previous_run_schemas() -> None:
    jobs = FakeJobs()
    jobs.latest = finished_job()
    service, _ = build(jobs)

    job = service.retry("warehouse", None, "u-1")

    assert job.schemas == ("shop", "billing")


def test_resuming_mid_pipeline_keeps_the_earlier_steps_results() -> None:
    jobs = FakeJobs()
    jobs.latest = finished_job()
    service, _ = build(jobs)

    job = service.retry("warehouse", "semantic_compile", "u-1")

    names = [s.name for s in job.steps]
    assert names == [
        "schema_registration",
        "discovery",
        "semantic_overlay",
        "semantic_compile",
        "graph_analysis",
        "domain_discovery",
    ]
    # Carried forward, not reset — discovery genuinely did run last time.
    assert job.step("discovery").status is StepStatus.SUCCEEDED  # type: ignore[union-attr]
    assert job.step("semantic_compile").status is StepStatus.PENDING  # type: ignore[union-attr]


def test_a_retry_from_a_step_nobody_defined_is_refused() -> None:
    service, jobs = build()

    with pytest.raises(UnknownIngestionStepError):
        service.retry("warehouse", "embed_everything", "u-1")

    assert jobs.submitted == []


def test_a_retry_for_an_unregistered_datasource_is_refused() -> None:
    service, jobs = build()

    with pytest.raises(UnknownDatasourceError):
        service.retry("nope", None, "u-1")

    assert jobs.submitted == []


def test_a_datasource_registered_by_the_cli_reports_that_it_has_no_job_yet() -> None:
    service, _ = build()

    with pytest.raises(NoIngestionJobError):
        service.status("warehouse")
