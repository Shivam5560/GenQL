"""One grounded LLM call per object, carrying that object's columns,
foreign keys, and sample values — not one call per object plus one per
column. All four dependencies are ports, so no database, no LLM, and no
network is needed here."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeVar

from pydantic import BaseModel

from genql.domain.entities.column import Column
from genql.domain.entities.column_enrichment import ColumnEnrichment
from genql.domain.entities.column_profile import ColumnProfile
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.domain.value_objects.object_type import ObjectType
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.services.semantic.object_profiling_service import ObjectProfilingService

T = TypeVar("T", bound=BaseModel)

REF = SchemaRef(datasource_name="local", schema_name="shop")
OBJECT = DatabaseObject(
    datasource_name="local", schema_name="shop", object_name="orders", object_type=ObjectType.TABLE
)
COLUMN = Column(
    datasource_name="local",
    schema_name="shop",
    object_name="orders",
    column_name="status",
    ordinal=1,
    data_type="text",
    is_nullable=False,
)


class FakeReader:
    def read_objects(self, ref: SchemaRef) -> Sequence[DatabaseObject]:
        return [OBJECT]

    def read_constraints(self, ref: SchemaRef) -> Sequence[Constraint]:
        return []

    def read_columns(self, ref: SchemaRef) -> Sequence[Column]:
        return [COLUMN]

    def read_column_profiles(self, ref: SchemaRef) -> Sequence[ColumnProfile]:
        return [
            ColumnProfile(
                datasource_name="local",
                schema_name="shop",
                object_name="orders",
                column_name="status",
                sample_values=("OPEN", "SHIPPED"),
            )
        ]


class FakeChatProvider:
    def complete(self, prompt: str, response_schema: type[T]) -> T:
        # Genuinely generic — validated against whatever schema the caller
        # passes, rather than hardcoding a return type the Protocol's
        # generic `type[T] -> T` signature couldn't otherwise be satisfied by.
        return response_schema.model_validate(
            {
                "description": "Customer orders.",
                "business_alias": "orders",
                "columns": [
                    {"column_name": "status", "description": "Order lifecycle state.", "unit": None}
                ],
            }
        )


class FakeEmbeddingProvider:
    def embed(self, texts: Sequence[str]) -> Sequence[tuple[float, ...]]:
        return [(0.1, 0.2)]


class FakeWriter:
    def __init__(self) -> None:
        self.objects: list[ObjectEnrichment] = []
        self.columns: list[ColumnEnrichment] = []

    def write_object_enrichment(self, enrichment: ObjectEnrichment) -> None:
        self.objects.append(enrichment)

    def write_column_enrichments(self, enrichments: Sequence[ColumnEnrichment]) -> int:
        self.columns.extend(enrichments)
        return len(enrichments)


def test_profile_writes_one_object_enrichment_with_its_embedding_and_its_columns() -> None:
    writer = FakeWriter()
    service = ObjectProfilingService(
        FakeReader(), FakeChatProvider(), FakeEmbeddingProvider(), writer
    )

    report = service.profile(REF, sample_limit=5)

    assert report.objects_profiled == 1
    assert report.columns_profiled == 1
    assert writer.objects[0].description == "Customer orders."
    assert writer.objects[0].embedding == (0.1, 0.2)
    assert writer.columns[0].description == "Order lifecycle state."
