"""Reads and writes registered datasources."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.datasource import Datasource


@runtime_checkable
class DatasourceRepository(Protocol):
    def add(self, datasource: Datasource) -> None: ...

    def get(self, name: str) -> Datasource: ...

    #: Writes an already-assembled row back. The caller reads, edits, and
    #: writes, so this port never has to know which fields an edit touched.
    def update(self, datasource: Datasource) -> None: ...

    def list_all(self, enabled_only: bool = False) -> Sequence[Datasource]: ...

    def remove(self, name: str) -> None: ...
