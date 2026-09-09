"""The job table, used as a durable queue.

`claim_next` is the whole reason this is not a list in memory. `FOR UPDATE
SKIP LOCKED` lets one worker take a row while another walks past it instead of
blocking on it, and because the claim and the status flip share a transaction,
a worker that dies between them has done neither.

`release_stale` is the other half of that guarantee: a process killed mid-run
leaves a RUNNING row nobody owns, and without a sweeper that datasource could
never be ingested again — the partial unique index would refuse every new job
for it.
"""

from __future__ import annotations

import json

from sqlalchemy import Engine, text
from sqlalchemy.engine.row import RowMapping
from sqlalchemy.sql.elements import TextClause

from genql.domain.entities.ingestion_job import IngestionJob, IngestionStep, JobStatus
from genql.domain.errors import UnknownIngestionJobError

_COLUMNS = """
    job_id, datasource_name, user_id, status, schemas_json, steps_json,
    error, error_step, created_at, started_at, finished_at
"""

_INSERT = text("""
    INSERT INTO genql.genql_ingestion_job
        (job_id, datasource_name, user_id, status, schemas_json, steps_json, created_at)
    VALUES (:job_id, :datasource_name, :user_id, :status,
            CAST(:schemas_json AS JSON), CAST(:steps_json AS JSON), :created_at)
""")

_SELECT_ONE = text(f"SELECT {_COLUMNS} FROM genql.genql_ingestion_job WHERE job_id = :job_id")

_SELECT_LATEST = text(f"""
    SELECT {_COLUMNS} FROM genql.genql_ingestion_job
    WHERE datasource_name = :datasource_name
    ORDER BY created_at DESC LIMIT 1
""")

_SELECT_LATEST_PER_DATASOURCE = text(f"""
    SELECT DISTINCT ON (datasource_name) {_COLUMNS}
    FROM genql.genql_ingestion_job
    ORDER BY datasource_name, created_at DESC
""")

_SELECT_ACTIVE = text(f"""
    SELECT {_COLUMNS} FROM genql.genql_ingestion_job
    WHERE datasource_name = :datasource_name AND status IN ('queued', 'running')
    ORDER BY created_at DESC LIMIT 1
""")

_CLAIM = text(f"""
    UPDATE genql.genql_ingestion_job SET
        status = 'running', claimed_by = :worker_id, claimed_at = now(), started_at = now()
    WHERE job_id = (
        SELECT job_id FROM genql.genql_ingestion_job
        WHERE status = 'queued'
        ORDER BY created_at
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING {_COLUMNS}
""")

_SELECT_STEPS = text("SELECT steps_json FROM genql.genql_ingestion_job WHERE job_id = :job_id")

_UPDATE_STEPS = text("""
    UPDATE genql.genql_ingestion_job SET steps_json = CAST(:steps_json AS JSON)
    WHERE job_id = :job_id RETURNING job_id
""")

_FINISH = text("""
    UPDATE genql.genql_ingestion_job SET
        status = :status, error = :error, error_step = :error_step, finished_at = now()
    WHERE job_id = :job_id RETURNING job_id
""")

_RELEASE_STALE = text("""
    UPDATE genql.genql_ingestion_job SET
        status = 'queued', claimed_by = NULL, claimed_at = NULL, started_at = NULL
    WHERE status = 'running'
      AND claimed_at < now() - make_interval(secs => :older_than_seconds)
    RETURNING job_id
""")


def _to_job(row: RowMapping) -> IngestionJob:
    return IngestionJob(
        job_id=row["job_id"],
        datasource_name=row["datasource_name"],
        user_id=row["user_id"],
        status=JobStatus(row["status"]),
        schemas=tuple(row["schemas_json"] or ()),
        steps=tuple(IngestionStep.model_validate(s) for s in (row["steps_json"] or ())),
        error=row["error"],
        error_step=row["error_step"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
    )


class PostgresIngestionJobRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def submit(self, job: IngestionJob) -> None:
        payload = {
            "job_id": job.job_id,
            "datasource_name": job.datasource_name,
            "user_id": job.user_id,
            "status": job.status.value,
            "schemas_json": json.dumps(list(job.schemas)),
            "steps_json": json.dumps([s.model_dump(mode="json") for s in job.steps]),
            "created_at": job.created_at,
        }
        with self._engine.begin() as conn:
            conn.execute(_INSERT, payload)

    def get(self, job_id: str) -> IngestionJob:
        with self._engine.connect() as conn:
            row = conn.execute(_SELECT_ONE, {"job_id": job_id}).one_or_none()
        if row is None:
            raise UnknownIngestionJobError(job_id)
        return _to_job(row._mapping)  # noqa: SLF001 - Row mapping is public API

    def latest_for_datasource(self, datasource_name: str) -> IngestionJob | None:
        return self._one(_SELECT_LATEST, {"datasource_name": datasource_name})

    def latest_per_datasource(self) -> tuple[IngestionJob, ...]:
        with self._engine.connect() as conn:
            rows = conn.execute(_SELECT_LATEST_PER_DATASOURCE).all()
        return tuple(_to_job(r._mapping) for r in rows)  # noqa: SLF001

    def active_for_datasource(self, datasource_name: str) -> IngestionJob | None:
        return self._one(_SELECT_ACTIVE, {"datasource_name": datasource_name})

    def claim_next(self, worker_id: str) -> IngestionJob | None:
        with self._engine.begin() as conn:
            row = conn.execute(_CLAIM, {"worker_id": worker_id}).one_or_none()
        return None if row is None else _to_job(row._mapping)  # noqa: SLF001

    def record_step(self, job_id: str, step: IngestionStep) -> None:
        """Read-modify-write one step inside the job's step list.

        Serialised by row lock rather than by optimistic retry: only the one
        worker holding this job ever writes its steps, so the lock is
        uncontended and the simplest correct thing.
        """
        with self._engine.begin() as conn:
            row = conn.execute(_SELECT_STEPS, {"job_id": job_id}).one_or_none()
            if row is None:
                raise UnknownIngestionJobError(job_id)
            steps = [IngestionStep.model_validate(s) for s in (row[0] or [])]
            replaced = [step if s.name == step.name else s for s in steps]
            if all(s.name != step.name for s in steps):
                replaced.append(step)
            conn.execute(
                _UPDATE_STEPS,
                {
                    "job_id": job_id,
                    "steps_json": json.dumps([s.model_dump(mode="json") for s in replaced]),
                },
            )

    def finish(
        self, job_id: str, status: JobStatus, error: str | None, error_step: str | None
    ) -> None:
        with self._engine.begin() as conn:
            updated = conn.execute(
                _FINISH,
                {
                    "job_id": job_id,
                    "status": status.value,
                    "error": error,
                    "error_step": error_step,
                },
            ).scalar()
        if updated is None:
            raise UnknownIngestionJobError(job_id)

    def release_stale(self, older_than_seconds: int) -> int:
        with self._engine.begin() as conn:
            released = conn.execute(
                _RELEASE_STALE, {"older_than_seconds": older_than_seconds}
            ).all()
        return len(released)

    def _one(self, statement: TextClause, params: dict[str, str]) -> IngestionJob | None:
        with self._engine.connect() as conn:
            row = conn.execute(statement, params).one_or_none()
        return None if row is None else _to_job(row._mapping)  # noqa: SLF001
