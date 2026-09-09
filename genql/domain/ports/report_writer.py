"""Serializes evaluation reports to a file, for the same reason
GoldenSetReader reads one: writing a file is I/O."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.golden_run_report import GoldenRunReport


@runtime_checkable
class ReportWriter(Protocol):
    def write(self, path: str, reports: tuple[GoldenRunReport, ...]) -> None: ...
