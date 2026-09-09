"""Persistence and queueing for ingestion jobs — deliberately one port.

A job table in Postgres *is* the queue: `claim_next` takes the oldest queued
row under `FOR UPDATE SKIP LOCKED` and flips it to running in the same
transaction, which is the standard way to get at-most-once dispatch without a
broker. Splitting this into a Repository and a Queue port would put the claim
on one side of the seam and the row it mutates on the other, and any real
implementation would have to hold both halves together anyway.

Swapping in a real broker later replaces this adapter, not this interface:
`submit` becomes a publish, `claim_next` becomes a consumer poll, and nothing
above the port changes.
"""

from __future__ import annotations

from typing import Protocol

from genql.domain.entities.ingestion_job import IngestionJob, IngestionStep, JobStatus


class IngestionJobRepository(Protocol):
    def submit(self, job: IngestionJob) -> None:
        """Persist a new job in the QUEUED state."""
        ...

    def get(self, job_id: str) -> IngestionJob:
        """Raise UnknownIngestionJobError if there is no such job."""
        ...

    def latest_for_datasource(self, datasource_name: str) -> IngestionJob | None: ...

    def latest_per_datasource(self) -> tuple[IngestionJob, ...]:
        """The most recent job for every datasource, newest first.

        One query rather than one per datasource: the app-wide event
        stream re-reads this on every poll to notice a warehouse becoming
        queryable, and N+1 there is N+1 on a timer.
        """
        ...

    def active_for_datasource(self, datasource_name: str) -> IngestionJob | None:
        """The QUEUED or RUNNING job for this datasource, if one exists."""
        ...

    def claim_next(self, worker_id: str) -> IngestionJob | None:
        """Atomically take the oldest queued job and mark it RUNNING.

        Returns None when the queue is empty. Two workers calling this
        concurrently never receive the same job.
        """
        ...

    def record_step(self, job_id: str, step: IngestionStep) -> None:
        """Overwrite one step's row in a job, leaving the others untouched."""
        ...

    def finish(
        self, job_id: str, status: JobStatus, error: str | None, error_step: str | None
    ) -> None: ...

    def release_stale(self, older_than_seconds: int) -> int:
        """Return jobs a dead worker left RUNNING to the queue.

        A process killed mid-ingestion leaves its row claimed forever; this is
        what makes the queue survive a restart rather than merely outlive the
        request that filled it. Returns how many were released.
        """
        ...
