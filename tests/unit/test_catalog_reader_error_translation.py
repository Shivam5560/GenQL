"""A warehouse failure must leave the reader as a typed domain error.

CatalogScanStep catches DiscoveryError. A raw DBAPIError sails straight past
that handler, out of the runner, and onto the user's terminal as a traceback,
taking the rest of the scope's schemas with it. PostgresProfileReaderRepository
already translates its failures into ProfilingError; this is the same contract
for the catalog side.
"""

from __future__ import annotations

from typing import Any, NoReturn

import pytest

from genql.domain.errors import CatalogAccessError, DiscoveryError
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.repositories.warehouse.catalog_reader_repository import (
    PostgresCatalogReaderRepository,
)

REF = SchemaRef(datasource_name="local", schema_name="shop")


class UnreachableEngine:
    def connect(self) -> NoReturn:
        raise OSError("connection to server at 10.0.0.1, port 5432 failed")


def _reader() -> PostgresCatalogReaderRepository:
    engine: Any = UnreachableEngine()
    return PostgresCatalogReaderRepository(engine)


@pytest.mark.parametrize("method", ["read_objects", "read_columns", "read_constraints"])
def test_every_read_translates_a_driver_failure(method: str) -> None:
    with pytest.raises(CatalogAccessError) as excinfo:
        getattr(_reader(), method)(REF)

    assert "local.shop" in str(excinfo.value)
    assert "connection to server" in str(excinfo.value)
    # The step's handler catches DiscoveryError, so the subclassing matters.
    assert isinstance(excinfo.value, DiscoveryError)
