"""SchemaRef is the identity every catalog row is keyed on."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genql.domain.value_objects.schema_ref import SchemaRef


def test_qualified_name_joins_datasource_and_schema() -> None:
    assert SchemaRef(datasource_name="local", schema_name="tpcds").qualified_name == "local.tpcds"


def test_schema_ref_is_frozen() -> None:
    ref = SchemaRef(datasource_name="local", schema_name="tpcds")
    with pytest.raises(ValidationError):
        ref.schema_name = "other"  # type: ignore[misc]


def test_schema_ref_is_hashable_so_it_can_key_a_dict() -> None:
    ref = SchemaRef(datasource_name="local", schema_name="tpcds")
    assert {ref: 1}[SchemaRef(datasource_name="local", schema_name="tpcds")] == 1
