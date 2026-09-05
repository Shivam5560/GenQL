"""Persists column profiles into the semantic store."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.column_profile import ColumnProfile


@runtime_checkable
class ProfileWriter(Protocol):
    def write_profiles(self, profiles: Sequence[ColumnProfile]) -> int: ...
