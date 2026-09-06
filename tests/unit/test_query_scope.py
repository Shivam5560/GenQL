"""A QueryScope names exactly one datasource. Cross-datasource is unrepresentable."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genql.domain.value_objects.query_scope import QueryScope
from genql.domain.value_objects.schema_ref import SchemaRef


def test_refs_yields_one_ref_per_schema() -> None:
    scope = QueryScope(datasource_name="local", schema_names=("tpcds", "shop"))

    assert scope.refs() == (
        SchemaRef(datasource_name="local", schema_name="tpcds"),
        SchemaRef(datasource_name="local", schema_name="shop"),
    )


def test_scope_rejects_an_empty_schema_list() -> None:
    with pytest.raises(ValidationError):
        QueryScope(datasource_name="local", schema_names=())


def test_scope_is_frozen() -> None:
    scope = QueryScope(datasource_name="local", schema_names=("tpcds",))
    with pytest.raises(ValidationError):
        scope.datasource_name = "wh2"  # type: ignore[misc]
