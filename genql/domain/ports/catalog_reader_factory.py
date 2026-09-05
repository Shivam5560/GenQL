"""Produces a CatalogReader bound to one datasource.

This is the seam that keeps multi-datasource discovery inside the layering. A
service must never see an Engine, a DSN, or a dialect, but it does need a
reader for a PARTICULAR warehouse. It loads the Datasource through a
repository port and hands it here; the infrastructure implementation resolves
the connection and the dialect.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.datasource import Datasource
from genql.domain.ports.catalog_reader import CatalogReader


@runtime_checkable
class CatalogReaderFactory(Protocol):
    def for_datasource(self, datasource: Datasource) -> CatalogReader: ...
