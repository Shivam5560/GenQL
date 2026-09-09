"""The ingestion streams make the same promises the query stream does: one
event per observable change, exactly one terminal event, nothing after it.

The polling is driven at zero delay here — the decisions are what matter, and
a test that waits on a real clock tests the clock.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from genql.api.sse.ingestion_events import (
    ingestion_event_stream,
    transitions,
)
from genql.domain.entities.ingestion_job import IngestionJob, IngestionStep, JobStatus, StepStatus


def make_job(
    status: JobStatus, steps: tuple[IngestionStep, ...] = (), **extra: object
) -> IngestionJob:
    return IngestionJob(
        job_id="j-1",
        datasource_name="warehouse",
        user_id="u-1",
        status=status,
        schemas=("shop",),
        steps=steps,
        created_at=datetime(2026, 9, 10, tzinfo=UTC),
        **extra,  # type: ignore[arg-type]
    )


class ScriptedJobs:
    """Hands out one job state per read, so a stream sees the job progress."""

    def __init__(self, states: list[IngestionJob]) -> None:
        self._states = states
        self._index = 0

    def get(self, _job_id: str) -> IngestionJob:
        state = self._states[min(self._index, len(self._states) - 1)]
        self._index += 1
        return state


def stream(states: list[IngestionJob]) -> list[dict[str, str]]:
    return list(ingestion_event_stream(ScriptedJobs(states), "j-1", poll_seconds=0))  # type: ignore[arg-type]


def names(events: list[dict[str, str]]) -> list[str]:
    return [e["event"] for e in events]


def test_a_finished_job_ends_with_exactly_one_done_event() -> None:
    steps = (IngestionStep(name="discovery", status=StepStatus.SUCCEEDED),)

    events = stream([make_job(JobStatus.SUCCEEDED, steps)])

    assert names(events).count("done") == 1
    assert names(events)[-1] == "done"


def test_a_failed_job_ends_with_an_error_carrying_the_step_that_broke() -> None:
    failed = make_job(
        JobStatus.FAILED,
        (IngestionStep(name="semantic_compile", status=StepStatus.FAILED),),
        error="CompileError: boom",
        error_step="semantic_compile",
    )

    events = stream([failed])

    assert names(events)[-1] == "error"
    payload = json.loads(events[-1]["data"])
    assert payload["error"] == "CompileError: boom"
    assert payload["step"] == "semantic_compile"


def test_progress_is_re_sent_only_when_something_actually_changed() -> None:
    running = make_job(
        JobStatus.RUNNING, (IngestionStep(name="discovery", status=StepStatus.RUNNING),)
    )
    advanced = make_job(
        JobStatus.RUNNING,
        (IngestionStep(name="discovery", status=StepStatus.SUCCEEDED, records_written=41),),
    )
    done = make_job(JobStatus.SUCCEEDED, advanced.steps)

    events = stream([running, running, advanced, done])

    # Three observed changes, so three step events — the repeated identical
    # poll in the middle emitted nothing.
    assert names(events) == ["step", "step", "step", "done"]


def test_a_step_event_carries_the_count_the_stage_reported() -> None:
    done = make_job(
        JobStatus.SUCCEEDED,
        (
            IngestionStep(
                name="semantic_compile",
                status=StepStatus.SUCCEEDED,
                detail="41 search documents embedded",
                records_written=41,
            ),
        ),
    )

    payload = json.loads(stream([done])[0]["data"])

    assert payload["name"] == "semantic_compile"
    assert payload["records_written"] == 41
    assert payload["detail"] == "41 search documents embedded"


def test_opening_the_feed_does_not_replay_completions_that_already_happened() -> None:
    seen: dict[str, str] = {}

    events = transitions([make_job(JobStatus.SUCCEEDED)], seen, seeded=False)

    assert events == []
    # The baseline is still recorded, so the same state never fires later.
    assert seen == {"warehouse": "succeeded"}


def test_a_datasource_that_becomes_ready_is_announced_once() -> None:
    seen: dict[str, str] = {}
    transitions([make_job(JobStatus.RUNNING)], seen, seeded=True)

    first = transitions([make_job(JobStatus.SUCCEEDED)], seen, seeded=True)
    again = transitions([make_job(JobStatus.SUCCEEDED)], seen, seeded=True)

    assert names(first) == ["ready"]
    assert json.loads(first[0]["data"])["datasource"] == "warehouse"
    assert again == []


def test_a_datasource_that_fails_is_announced_with_its_error() -> None:
    seen = {"warehouse": "running"}

    events = transitions(
        [make_job(JobStatus.FAILED, error="CompileError: boom", error_step="semantic_compile")],
        seen,
        seeded=True,
    )

    assert names(events) == ["failed"]
    payload = json.loads(events[0]["data"])
    assert payload["error"] == "CompileError: boom"
    assert payload["error_step"] == "semantic_compile"
