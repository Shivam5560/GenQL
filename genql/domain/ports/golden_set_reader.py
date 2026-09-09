"""Reads hand-curated cases from disk.

A port because file I/O is I/O: a service never opens a file, exactly as it
never opens a cursor. That is also what lets GoldenEvaluationService be unit
tested with a tuple of cases and no filesystem.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.golden_case import GoldenCase


@runtime_checkable
class GoldenSetReader(Protocol):
    def read_cases(self, datasource_name: str | None = None) -> tuple[GoldenCase, ...]: ...
