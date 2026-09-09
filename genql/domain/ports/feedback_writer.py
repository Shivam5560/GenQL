"""Persists one rating."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.feedback import Feedback


@runtime_checkable
class FeedbackWriter(Protocol):
    def write(self, feedback: Feedback) -> None: ...
