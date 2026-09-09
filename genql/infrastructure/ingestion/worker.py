"""The process that actually ingests warehouses.

A daemon thread inside the API process, not a separate service. That is the
right size for the current single-node target and it is honest about its
limits: the queue is durable (Postgres), the worker is not (a restart kills
the run mid-step). What makes that survivable is `release_stale` — a job whose
worker died is returned to the queue on the next sweep rather than being
stuck RUNNING forever, which the partial unique index would otherwise read as
"this datasource is already being ingested" for good.

Moving this into its own process later changes this file and nothing else:
everything it calls is already reachable from a plain container.
"""

from __future__ import annotations

import os
import threading
import uuid
from collections.abc import Callable

import structlog

from genql.domain.entities.ingestion_job import IngestionJob, IngestionStep, JobStatus
from genql.domain.errors import GenqlError
from genql.domain.ports.ingestion_job_repository import IngestionJobRepository
from genql.services.datasource.ingestion_service import IngestionService

_log = structlog.get_logger(__name__)


class IngestionWorker:
    def __init__(  # noqa: PLR0913, PLR0917 - one knob each, all with defaults
        self,
        jobs: IngestionJobRepository,
        ingestion: Callable[[], IngestionService],
        poll_seconds: float = 1.0,
        stale_after_seconds: int = 900,
        sweep_every: int = 60,
    ) -> None:
        self._jobs = jobs
        self._ingestion = ingestion
        self._poll_seconds = poll_seconds
        self._stale_after_seconds = stale_after_seconds
        self._sweep_every = sweep_every
        self._worker_id = f"{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._loop, name="genql-ingestion", daemon=True)
        self._thread.start()
        _log.info("ingestion.worker.started", worker_id=self._worker_id)

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _loop(self) -> None:
        ticks = 0
        while not self._stop.is_set():
            if ticks % self._sweep_every == 0:
                self._sweep()
            ticks += 1
            # A tick that found work goes straight back for more: a queue of
            # five datasources should not take five seconds to start the second.
            if not self.run_once():
                self._stop.wait(self._poll_seconds)

    def _sweep(self) -> None:
        try:
            released = self._jobs.release_stale(self._stale_after_seconds)
        except Exception:
            _log.exception("ingestion.worker.sweep_failed")
            return
        if released:
            _log.warning("ingestion.worker.released_stale", jobs=released)

    def run_once(self) -> bool:
        """Claim one job and run it to completion. Returns whether one ran.

        Public because the CLI's `datasource onboard --wait` drains the queue
        with it, and because a test can drive one job without a thread.
        """
        try:
            job = self._jobs.claim_next(self._worker_id)
        except Exception:
            _log.exception("ingestion.worker.claim_failed")
            return False
        if job is None:
            return False
        self._run(job)
        return True

    def _run(self, job: IngestionJob) -> None:
        log = _log.bind(job_id=job.job_id, datasource=job.datasource_name)
        log.info("ingestion.job.start", schemas=list(job.schemas))
        pending = tuple(s for s in job.steps if s.status.value in ("pending", "failed"))

        def report(step: IngestionStep) -> None:
            self._jobs.record_step(job.job_id, step)

        try:
            self._ingestion().run(job.datasource_name, job.schemas, pending, report)
        except GenqlError as exc:
            self._fail(job, log, exc)
            return
        except Exception as exc:  # noqa: BLE001 - a bug must not kill the worker thread
            self._fail(job, log, exc)
            return

        self._jobs.finish(job.job_id, JobStatus.SUCCEEDED, None, None)
        log.info("ingestion.job.succeeded")

    def _fail(self, job: IngestionJob, log: structlog.BoundLogger, exc: Exception) -> None:
        """Record the failure against the step that raised it.

        Re-reading the job is what makes `error_step` accurate: the service
        already wrote that step as FAILED before re-raising, so the store —
        not this thread's local copy — knows which one it was.
        """
        failed_at = None
        try:
            failed_at = next(
                (s.name for s in self._jobs.get(job.job_id).steps if s.status.value == "failed"),
                None,
            )
        except Exception:
            log.exception("ingestion.job.reread_failed")
        message = f"{type(exc).__name__}: {exc}"
        self._jobs.finish(job.job_id, JobStatus.FAILED, message, failed_at)
        log.warning("ingestion.job.failed", step=failed_at, error=message)
