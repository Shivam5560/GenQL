"""The one line of logic: a correction that is not a SELECT is refused.

The corrected SQL is what a later phase will index as a hint, so garbage
admitted here becomes garbage retrieved later — and unlike the generated SQL,
nothing else validates it."""

from __future__ import annotations

import pytest

from genql.domain.entities.feedback import Feedback
from genql.domain.errors import FeedbackError
from genql.services.semantic.feedback_service import FeedbackService


class _Writer:
    def __init__(self) -> None:
        self.written: list[Feedback] = []

    def write(self, feedback: Feedback) -> None:
        self.written.append(feedback)


def test_a_rating_without_a_correction_is_recorded() -> None:
    writer = _Writer()
    FeedbackService(writer).record(Feedback(thread_id="t-1", rating="good"))

    assert writer.written[0].thread_id == "t-1"


def test_a_correction_that_parses_as_a_select_is_recorded() -> None:
    writer = _Writer()
    feedback = Feedback(
        thread_id="t-1", rating="bad", corrected_sql="SELECT count(*) FROM tpcds.customer"
    )

    FeedbackService(writer).record(feedback)

    assert writer.written[0].corrected_sql is not None


def test_a_correction_that_is_not_a_select_is_refused() -> None:
    feedback = Feedback(thread_id="t-1", rating="bad", corrected_sql="DROP TABLE customer")

    with pytest.raises(FeedbackError):
        FeedbackService(_Writer()).record(feedback)


def test_a_correction_that_does_not_parse_is_refused() -> None:
    feedback = Feedback(thread_id="t-1", rating="bad", corrected_sql="SELECT FROM WHERE")

    with pytest.raises(FeedbackError):
        FeedbackService(_Writer()).record(feedback)


def test_a_refused_correction_is_never_written() -> None:
    writer = _Writer()
    feedback = Feedback(thread_id="t-1", rating="bad", corrected_sql="DELETE FROM customer")

    with pytest.raises(FeedbackError):
        FeedbackService(writer).record(feedback)

    assert writer.written == []
