"""Samples real values and statistics for one column."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.column import Column
from genql.domain.entities.column_profile import ColumnProfile


@runtime_checkable
class ProfileReader(Protocol):
    def profile_column(self, column: Column, sample_limit: int) -> ColumnProfile: ...
