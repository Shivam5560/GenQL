from __future__ import annotations

import pytest
from pydantic import ValidationError

from genql.domain.entities.join_path import JoinPath
from genql.domain.value_objects.provenance import Provenance


def test_join_path_defaults_to_discovered_provenance() -> None:
    path = JoinPath(
        datasource_name="local",
        schema_name="tpcds",
        source_object="store_sales",
        target_object="date_dim",
        path=("store_sales", "date_dim"),
        weight=1.0,
    )
    assert path.provenance == Provenance.DISCOVERED


def test_join_path_is_frozen() -> None:
    path = JoinPath(
        datasource_name="local",
        schema_name="tpcds",
        source_object="store_sales",
        target_object="date_dim",
        path=("store_sales", "date_dim"),
        weight=1.0,
    )
    with pytest.raises(ValidationError):
        path.weight = 2.0  # type: ignore[misc]
