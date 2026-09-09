"""Submits ingestion jobs and reports on them. Never runs one.

This is the half of onboarding that answers a request in milliseconds:
register the datasource, write a QUEUED job, hand back a job id. The stages
themselves run in a worker draining the same job table, which is why
`POST /v1/datasources` can return 202 while a 400-table warehouse is still
being profiled ten minutes later.

Registration stays synchronous on purpose. A bad dialect or an unset DSN
variable is the caller's mistake and belongs in the response to their request,
not in a job that fails thirty seconds later somewhere they are not looking.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from genql.domain.entities.datasource import Datasource
from genql.domain.entities.ingestion_job import (
    STEP_SEQUENCE,
    IngestionJob,
    IngestionStep,
    JobStatus,
    pending_steps,
)
from genql.domain.errors import (
    IngestionInProgressError,
    NoIngestionJobError,
    UnknownIngestionStepError,
)
from genql.domain.ports.clock import Clock
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.domain.ports.ingestion_job_repository import IngestionJobRepository
from genql.services.datasource.datasource_service import DatasourceService


class OnboardingService:
    def __init__(
        self,
        datasources: DatasourceService,
        datasource_repository: DatasourceRepository,
        jobs: IngestionJobRepository,
        clock: Clock,
    ) -> None:
        self._datasources = datasources
        self._repository = datasource_repository
        self._jobs = jobs
        self._clock = clock

    def register_and_submit(  # noqa: PLR0913, PLR0917 - mirrors the registration form
        self,
        name: str,
        dialect: str,
        dsn_env_var: str,
        description: str | None,
        schemas: Sequence[str],
        user_id: str,
    ) -> tuple[Datasource, IngestionJob]:
        """Register the datasource, then queue its ingestion.

        Both happen before returning, and only the second is asynchronous:
        by the time the caller sees a 202 the datasource row exists, so an
        immediate GET /v1/datasources lists it — as "ingesting", not as ready.
        """
        datasource = self._datasources.register(name, dialect, dsn_env_var, description)
        return datasource, self._queue(name, tuple(schemas), user_id, start_from=None)

    def retry(self, datasource_name: str, start_from: str | None, user_id: str) -> IngestionJob:
        """Queue a fresh run, optionally resuming from one step forward.

        The schemas come from the last job rather than from the caller, so a
        retry cannot quietly change the scope of what is being ingested.
        """
        if start_from is not None and start_from not in STEP_SEQUENCE:
            raise UnknownIngestionStepError(start_from, STEP_SEQUENCE)
        # Proves the datasource exists before anything is queued: a job for a
        # name nobody registered would fail in the worker, minutes later.
        self._repository.get(datasource_name)
        previous = self._jobs.latest_for_datasource(datasource_name)
        schemas = previous.schemas if previous is not None else ()
        return self._queue(datasource_name, schemas, user_id, start_from, previous)

    def status(self, datasource_name: str) -> IngestionJob:
        self._repository.get(datasource_name)
        job = self._jobs.latest_for_datasource(datasource_name)
        if job is None:
            raise NoIngestionJobError(datasource_name)
        return job

    def _queue(  # noqa: PLR0913, PLR0917 - all five are one job's identity
        self,
        datasource_name: str,
        schemas: tuple[str, ...],
        user_id: str,
        start_from: str | None,
        previous: IngestionJob | None = None,
    ) -> IngestionJob:
        active = self._jobs.active_for_datasource(datasource_name)
        if active is not None:
            raise IngestionInProgressError(datasource_name, active.job_id)
        job = IngestionJob(
            job_id=uuid.uuid4().hex,
            datasource_name=datasource_name,
            user_id=user_id,
            status=JobStatus.QUEUED,
            schemas=schemas,
            steps=self._carry_forward(start_from, previous),
            created_at=self._clock.now(),
        )
        self._jobs.submit(job)
        return job

    @staticmethod
    def _carry_forward(
        start_from: str | None, previous: IngestionJob | None
    ) -> tuple[IngestionStep, ...]:
        """Keep the skipped steps' earlier outcomes visible on a resumed job.

        Without this a run resumed at `semantic_compile` reports discovery as
        "pending" forever, which reads as though it never happened.
        """
        fresh = pending_steps(start_from)
        if start_from is None or previous is None:
            return fresh
        kept = STEP_SEQUENCE[: STEP_SEQUENCE.index(start_from)]
        carried = tuple(step for name in kept if (step := previous.step(name)) is not None)
        return carried + fresh
