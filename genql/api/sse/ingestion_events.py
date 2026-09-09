"""The generators behind the two ingestion streams.

Progress is read from the job store rather than pushed from the worker. That
looks like the lazier choice and is in fact the more honest one: the worker
may not share a process with the request being served — today it is a thread,
tomorrow it is a container — and an in-process pub/sub would silently stop
working the moment that changes. Polling a durable row works either way, and
one query a second per watcher is nothing next to the minutes of warehouse
I/O it is reporting on.

Every decision about *what* to emit lives in a pure function here; the
generators only add the poll and the sleep. That split is what keeps these
testable — a test drives the decisions directly instead of waiting on a clock.

Same three guarantees the query stream makes: one event per observable
change, exactly one terminal event (`done` or `error`), and nothing after it.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator, Sequence
from typing import Any

from genql.api.dtos.datasource_dtos import IngestionJobDto, IngestionStepDto
from genql.domain.entities.ingestion_job import IngestionJob, JobStatus
from genql.domain.ports.ingestion_job_repository import IngestionJobRepository

JOB_POLL_SECONDS = 0.75
#: Deliberately slower: this one is a background subscription for the whole
#: tab, not a progress bar somebody is watching.
FEED_POLL_SECONDS = 3.0
#: A watcher that outlives this is watching a job the worker has abandoned.
#: The stream ends rather than holding a thread open indefinitely; the client
#: reconnects or falls back to the plain GET.
MAX_JOB_SECONDS = 60 * 45


def _event(name: str, payload: dict[str, Any]) -> dict[str, str]:
    return {"event": name, "data": json.dumps(payload, default=str)}


def fingerprint(job: IngestionJob) -> str:
    """What "something changed" means: the job's status plus every step's."""
    steps = ";".join(f"{s.name}:{s.status.value}:{s.records_written}" for s in job.steps)
    return f"{job.status.value}|{steps}"


def step_events(job: IngestionJob) -> list[dict[str, str]]:
    return [
        _event(
            "step",
            {
                "job_id": job.job_id,
                "datasource": job.datasource_name,
                **IngestionStepDto.from_domain(step).model_dump(),
            },
        )
        for step in job.steps
    ]


def terminal_event(job: IngestionJob) -> dict[str, str]:
    payload = IngestionJobDto.from_domain(job).model_dump()
    if job.status is JobStatus.FAILED:
        return _event(
            "error",
            {
                "error": job.error or "IngestionError",
                "detail": job.error or "ingestion failed",
                "step": job.error_step,
                "job": payload,
            },
        )
    return _event("done", {"datasource": job.datasource_name, "job": payload})


def transitions(
    jobs: Sequence[IngestionJob], seen: dict[str, str], seeded: bool
) -> list[dict[str, str]]:
    """Which datasources just became queryable, or just failed.

    Mutates `seen` so the caller carries the baseline between polls. When
    `seeded` is False nothing is emitted at all: opening a tab must not replay
    every ingestion that ever finished as though it had just happened.
    """
    events: list[dict[str, str]] = []
    for job in jobs:
        state = job.status.value
        if seen.get(job.datasource_name) == state:
            continue
        seen[job.datasource_name] = state
        if not seeded or not job.terminal:
            continue
        events.append(
            _event(
                "ready" if job.status is JobStatus.SUCCEEDED else "failed",
                {
                    "datasource": job.datasource_name,
                    "job_id": job.job_id,
                    "error": job.error,
                    "error_step": job.error_step,
                },
            )
        )
    return events


def ingestion_event_stream(
    jobs: IngestionJobRepository,
    job_id: str,
    poll_seconds: float = JOB_POLL_SECONDS,
    max_seconds: float = MAX_JOB_SECONDS,
) -> Iterator[dict[str, str]]:
    """Stream one job's progress until it reaches a terminal state."""
    deadline = time.monotonic() + max_seconds
    previous: str | None = None

    while time.monotonic() < deadline:
        job = jobs.get(job_id)
        current = fingerprint(job)
        if current != previous:
            previous = current
            yield from step_events(job)
        if job.terminal:
            yield terminal_event(job)
            return
        time.sleep(poll_seconds)

    yield _event(
        "error",
        {
            "error": "IngestionStreamTimeout",
            "detail": "stopped watching this job; poll the onboarding endpoint instead",
            "step": None,
            "job": IngestionJobDto.from_domain(jobs.get(job_id)).model_dump(),
        },
    )


def datasource_event_stream(
    jobs: IngestionJobRepository, poll_seconds: float = FEED_POLL_SECONDS
) -> Iterator[dict[str, str]]:
    """The app-wide notification channel.

    One long-lived subscription per open browser tab, carrying only
    transitions: a datasource that becomes queryable, and one that fails. The
    UI holds this open for the whole session so "your warehouse is ready" can
    arrive on whatever page the person happens to be on, minutes after they
    submitted it and long after they navigated away from the form.
    """
    seen: dict[str, str] = {}
    seeded = False

    while True:
        yield from transitions(jobs.latest_per_datasource(), seen, seeded)
        seeded = True
        time.sleep(poll_seconds)
