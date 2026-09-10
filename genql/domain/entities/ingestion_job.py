"""One datasource's journey from "registered" to "queryable".

Registering a datasource writes a row; making it answerable takes six further
stages that talk to the warehouse, an LLM, and Neo4j, and together run for
minutes. That work is a *job*, not a request: it is submitted, it survives the
process that submitted it, and its progress is something a client polls or
streams rather than waits on.

The step names below are the contract the UI renders and the retry endpoint
accepts. They are deliberately coarser than the five discovery steps inside
`DISCOVERY_STEPS` — a person watching a warehouse come online cares that
"discovery" is running, not that `object_profiling` is the third of five —
and `IngestionStep.detail` carries the finer story as one short line.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class StepStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    # A step that had nothing to do — no overlay file on disk, say — is not a
    # failure and must not read as one, but it is also not the same as having
    # done the work, so it gets its own state rather than borrowing SUCCEEDED.
    SKIPPED = "skipped"
    FAILED = "failed"


SCHEMA_REGISTRATION = "schema_registration"
DISCOVERY = "discovery"
SEMANTIC_OVERLAY = "semantic_overlay"
SEMANTIC_COMPILE = "semantic_compile"
GRAPH_ANALYSIS = "graph_analysis"
DOMAIN_DISCOVERY = "domain_discovery"

#: The pipeline, in the only order that works: discovery must have written a
#: catalog before the search index can compile from it, and the graph must be
#: projected (a discovery step) before Leiden and FastRP have anything to run
#: on. `retry(start_from=...)` slices this tuple, so its order is load-bearing.
STEP_SEQUENCE: tuple[str, ...] = (
    SCHEMA_REGISTRATION,
    DISCOVERY,
    SEMANTIC_OVERLAY,
    SEMANTIC_COMPILE,
    GRAPH_ANALYSIS,
    DOMAIN_DISCOVERY,
)


class IngestionStep(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    status: StepStatus = StepStatus.PENDING
    #: One short human line — "41 objects in 3 schemas", "no overlay file".
    #: Never the payload itself, same rule as StageEvent.detail.
    detail: str | None = None
    records_written: int = 0
    duration_ms: int = 0


class IngestionJob(BaseModel):
    model_config = ConfigDict(frozen=True)

    job_id: str
    datasource_name: str
    #: Who submitted it. Ingestion is not scoped per user — a warehouse is
    #: shared — but the notification stream is, so the submitter is recorded.
    user_id: str
    status: JobStatus
    schemas: tuple[str, ...]
    steps: tuple[IngestionStep, ...]
    #: Set only when `status` is FAILED, and always the error *type* plus its
    #: message, so a client can branch on the type without parsing prose.
    error: str | None = None
    error_step: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @property
    def terminal(self) -> bool:
        return self.status in (JobStatus.SUCCEEDED, JobStatus.FAILED)

    @property
    def progress(self) -> float:
        """How far through the pipeline this job is, 0.0 to 1.0.

        Counted over STEP_SEQUENCE, not over `self.steps`: a job resumed at
        `semantic_compile` carries three steps, and reporting "1 of 3 done"
        would show a warehouse two thirds of the way through its survey as
        one third. A running step counts as half — the six steps are wildly
        unequal in length and discovery alone can be minutes, so a bar that
        sits perfectly still through it reads as a hang.

        SKIPPED counts as done, because it is: the step had nothing to do.
        """
        done = sum(
            1.0
            if step.status in (StepStatus.SUCCEEDED, StepStatus.SKIPPED)
            else 0.5
            if step.status is StepStatus.RUNNING
            else 0.0
            for step in self.steps
        )
        if self.status is JobStatus.SUCCEEDED:
            return 1.0
        return min(done / len(STEP_SEQUENCE), 1.0)

    def step(self, name: str) -> IngestionStep | None:
        return next((s for s in self.steps if s.name == name), None)


def pending_steps(start_from: str | None = None) -> tuple[IngestionStep, ...]:
    """The step list a fresh (or retried) job starts with.

    A retry keeps the earlier steps' recorded outcomes out of this list on
    purpose: the caller merges them back, so a re-run from `semantic_compile`
    still shows what discovery found the first time instead of blanking it.
    """
    names = STEP_SEQUENCE
    if start_from is not None:
        names = STEP_SEQUENCE[STEP_SEQUENCE.index(start_from) :]
    return tuple(IngestionStep(name=name) for name in names)
