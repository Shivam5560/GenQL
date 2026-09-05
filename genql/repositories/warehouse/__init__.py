"""Registers every warehouse reader with its dialect registry.

This is the one place that imports the reader modules purely for their
`@CATALOG_READERS.register(...)` / `@PROFILE_READERS.register(...)` decorator
side effect, mirroring how `genql.discovery.steps` registers discovery steps.
"""

from __future__ import annotations

from genql.repositories.warehouse.catalog_reader_repository import (
    PostgresCatalogReaderRepository,
)
from genql.repositories.warehouse.profile_reader_repository import (
    PostgresProfileReaderRepository,
)

__all__ = ["PostgresCatalogReaderRepository", "PostgresProfileReaderRepository"]
