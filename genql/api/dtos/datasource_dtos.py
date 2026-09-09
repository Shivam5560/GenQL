"""The wire contract for the datasource routes.

`dsn_env_var` is omitted: it names the environment variable holding a
warehouse credential, and even the variable's name is not something a client
of this API needs or should see.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from genql.domain.entities.datasource import Datasource
from genql.domain.entities.ingestion_job import IngestionJob, IngestionStep


class DatasourceDto(BaseModel):
    name: str
    dialect: str
    description: str | None = None
    enabled: bool = True

    @classmethod
    def from_domain(cls, datasource: Datasource) -> DatasourceDto:
        return cls(
            name=datasource.name,
            dialect=datasource.dialect,
            description=datasource.description,
            enabled=datasource.enabled,
        )


class RegisterDatasourceRequest(BaseModel):
    name: str
    dialect: str = "postgres"
    #: The NAME of an environment variable, never a connection string. The
    #: server reads the DSN from its own environment at connect time, so a
    #: warehouse credential never crosses this API in either direction.
    dsn_env_var: str
    description: str | None = None
    #: Schemas to ingest. Empty means "whatever the scope resolver defaults
    #: to", which is the single-schema case the CLI has always supported.
    schemas: list[str] = []


class RetryIngestionRequest(BaseModel):
    #: One of IngestionJob's STEP_SEQUENCE names. Omitted re-runs everything.
    start_from: str | None = None


class IngestionStepDto(BaseModel):
    name: str
    status: str
    detail: str | None = None
    records_written: int = 0
    duration_ms: int = 0

    @classmethod
    def from_domain(cls, step: IngestionStep) -> IngestionStepDto:
        return cls(
            name=step.name,
            status=step.status.value,
            detail=step.detail,
            records_written=step.records_written,
            duration_ms=step.duration_ms,
        )


class IngestionJobDto(BaseModel):
    job_id: str
    datasource_name: str
    status: str
    schemas: list[str] = []
    steps: list[IngestionStepDto] = []
    error: str | None = None
    error_step: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @classmethod
    def from_domain(cls, job: IngestionJob) -> IngestionJobDto:
        return cls(
            job_id=job.job_id,
            datasource_name=job.datasource_name,
            status=job.status.value,
            schemas=list(job.schemas),
            steps=[IngestionStepDto.from_domain(s) for s in job.steps],
            error=job.error,
            error_step=job.error_step,
            created_at=job.created_at,
            started_at=job.started_at,
            finished_at=job.finished_at,
        )


class DatasourceAcceptedDto(BaseModel):
    """The 202 body. Says what was created and where to watch it happen."""

    datasource: DatasourceDto
    job: IngestionJobDto
    stream_url: str
