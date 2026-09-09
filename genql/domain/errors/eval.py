"""Failures raised by the golden-set runner, the ablation harness, and
feedback capture (Phase 8)."""

from __future__ import annotations

from genql.domain.errors.base import GenqlError


class EvaluationError(GenqlError):
    """The golden-set runner or the ablation harness could not complete."""


class GoldenSetError(EvaluationError):
    """A fixture file is missing, malformed, or names an unknown failure class."""


class UnknownAblationError(EvaluationError):
    def __init__(self, name: str, known: list[str]) -> None:
        super().__init__(f"unknown ablation {name!r}; registered: {', '.join(known)}")
        self.name = name


class FeedbackError(GenqlError):
    """Feedback could not be accepted or recorded."""
