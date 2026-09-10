"""The wire contract for the datasource routes.

The password travels in exactly one direction. `RegisterDatasourceRequest`
carries it inbound, over whatever TLS the deployment terminates; `DatasourceDto`
has no field for it and no `from_domain` branch that could add one, so no
response, log line, or client cache can hold it. `endpoint` is the printable
half — `host:port/database` — which is what a person needs in order to confirm
they connected the right warehouse.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from genql.domain.entities.datasource import Datasource
from genql.domain.entities.ingestion_job import IngestionJob, IngestionStep
from genql.domain.value_objects.datasource_connection import DatasourceConnection
from genql.domain.value_objects.datasource_update import DatasourceUpdate


class DatasourceDto(BaseModel):
    name: str
    dialect: str
    description: str | None = None
    enabled: bool = True
    #: `host:port/database`, or None for a datasource that reads its DSN from
    #: the server environment.
    endpoint: str | None = None

    @classmethod
    def from_domain(cls, datasource: Datasource) -> DatasourceDto:
        return cls(
            name=datasource.name,
            dialect=datasource.dialect,
            description=datasource.description,
            enabled=datasource.enabled,
            endpoint=datasource.endpoint,
        )


class RegisterDatasourceRequest(BaseModel):
    name: str
    dialect: str = "postgres"
    host: str
    port: int = Field(default=5432, gt=0, le=65535)
    database: str
    username: str
    #: Encrypted the moment it lands and never read back out of this API.
    password: str = ""
    #: Driver query string — `sslmode=require`, `connect_timeout=10`. Passed
    #: through verbatim because which options are legal is the driver's
    #: business, not this schema's.
    options: str | None = None
    description: str | None = None
    #: Schemas to ingest. Empty means "whatever the scope resolver defaults
    #: to", which is the single-schema case the CLI has always supported.
    schemas: list[str] = []

    def to_connection(self) -> DatasourceConnection:
        return DatasourceConnection(
            host=self.host.strip(),
            port=self.port,
            database=self.database.strip(),
            username=self.username.strip(),
            password=self.password,
            options=(self.options or "").strip() or None,
        )


class UpdateDatasourceRequest(BaseModel):
    """A partial edit. Absent means "leave alone"; `""` clears a text field.

    The name is not here: it is the identity every catalog row, profile and
    ingestion job references, so an edit moves where a datasource points, not
    what it is called.
    """

    dialect: str | None = None
    dsn_env_var: str | None = None
    host: str | None = None
    port: int | None = Field(default=None, gt=0, le=65535)
    database: str | None = None
    username: str | None = None
    #: Write-only, like on registration. Sending "" forgets the stored one.
    password: str | None = None
    options: str | None = None
    description: str | None = None
    enabled: bool | None = None

    def to_patch(self) -> DatasourceUpdate:
        return DatasourceUpdate(**self.model_dump(exclude_unset=True))


class DialectsDto(BaseModel):
    """What a client may offer in a dialect picker, per the reader registry."""

    dialects: list[str]


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
    #: 0.0-1.0 across the whole six-step pipeline, so a client can draw a bar
    #: without knowing what the steps are or how many there should be.
    progress: float = 0.0
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
            progress=job.progress,
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
