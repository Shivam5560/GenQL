"""Failures raised while submitting or running a datasource ingestion job."""

from __future__ import annotations

from genql.domain.errors.base import GenqlError


class IngestionError(GenqlError):
    """An ingestion job could not be submitted or resumed."""


class UnknownIngestionJobError(IngestionError):
    def __init__(self, job_id: str) -> None:
        super().__init__(f"{job_id!r} is not a known ingestion job")
        self.job_id = job_id


class NoIngestionJobError(IngestionError):
    """A datasource exists but has never been ingested.

    Distinct from UnknownIngestionJobError, which means a job id was wrong.
    This one means the datasource was registered outside the onboarding
    endpoint — by the CLI, or by an older release — so there is no job row to
    report progress from, and the fix is to run one.
    """

    def __init__(self, datasource_name: str) -> None:
        super().__init__(
            f"datasource {datasource_name!r} has no ingestion job on record; "
            "submit one with POST /v1/datasources/{name}/onboarding/retry"
        )
        self.datasource_name = datasource_name


class IngestionInProgressError(IngestionError):
    """A second job was submitted for a datasource already being ingested.

    Refused rather than queued: the stages write to the same catalog rows and
    the same graph projection, so two concurrent runs over one datasource
    interleave into a catalog that matches neither.
    """

    def __init__(self, datasource_name: str, job_id: str) -> None:
        super().__init__(
            f"datasource {datasource_name!r} is already being ingested by job {job_id!r}"
        )
        self.datasource_name = datasource_name
        self.job_id = job_id


class UnknownIngestionStepError(IngestionError):
    def __init__(self, step_name: str, available: tuple[str, ...]) -> None:
        options = ", ".join(available)
        super().__init__(f"{step_name!r} is not an ingestion step. Available: {options}")
        self.step_name = step_name
