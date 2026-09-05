from __future__ import annotations

import pytest
from pydantic import ValidationError

from genql.domain.entities.column import Column
from genql.domain.entities.column_profile import ColumnProfile
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.object_type import ObjectType


def test_database_object_is_frozen() -> None:
    obj = DatabaseObject(
        datasource_name="local",
        schema_name="public",
        object_name="store_sales",
        object_type=ObjectType.TABLE,
        row_estimate=2_880_404,
    )
    with pytest.raises(ValidationError):
        obj.object_name = "other"  # type: ignore[misc]


def test_qualified_name_joins_schema_and_object() -> None:
    obj = DatabaseObject(
        datasource_name="local",
        schema_name="public",
        object_name="store_sales",
        object_type=ObjectType.TABLE,
    )
    assert obj.qualified_name == "local.public.store_sales"


def test_column_qualified_name_includes_column() -> None:
    column = Column(
        datasource_name="local",
        schema_name="public",
        object_name="store_sales",
        column_name="ss_ext_sales_price",
        ordinal=14,
        data_type="numeric(7,2)",
        is_nullable=True,
    )
    assert column.qualified_name == "local.public.store_sales.ss_ext_sales_price"
    assert column.is_primary_key is False


def test_null_fraction_must_be_a_proportion() -> None:
    with pytest.raises(ValidationError):
        ColumnProfile(
            datasource_name="local",
            schema_name="public",
            object_name="store_sales",
            column_name="ss_item_sk",
            distinct_count=18_000,
            null_fraction=1.4,
        )


def test_sample_values_are_immutable() -> None:
    profile = ColumnProfile(
        datasource_name="local",
        schema_name="public",
        object_name="store",
        column_name="s_state",
        distinct_count=13,
        null_fraction=0.0,
        sample_values=("CA", "OR", "WA"),
    )
    assert isinstance(profile.sample_values, tuple)
    assert profile.sample_values[0] == "CA"
