"""Produces a ProfileReader bound to one datasource."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.datasource import Datasource
from genql.domain.ports.profile_reader import ProfileReader


@runtime_checkable
class ProfileReaderFactory(Protocol):
    def for_datasource(self, datasource: Datasource) -> ProfileReader: ...
