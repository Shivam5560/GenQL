"""Appends one measured execution to the evidence table."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.rewrite_outcome import RewriteOutcome


@runtime_checkable
class RewriteOutcomeWriter(Protocol):
    def write(self, outcome: RewriteOutcome) -> None: ...
