"""Reads and writes registered datasources."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from genql.domain.entities.datasource import Datasource


@runtime_checkable
class DatasourceRepository(Protocol):
    def add(self, datasource: Datasource) -> None: ...

    def get(self, name: str) -> Datasource: ...

    def list_all(self, enabled_only: bool = False) -> Sequence[Datasource]: ...

    def remove(self, name: str) -> None: ...
