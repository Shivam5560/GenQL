"""One repository for both tables: object and column enrichment are always
read and written together for one object, same rule as every other
aggregate-scoped repository in this codebase."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Engine

from genql.domain.entities.column_enrichment import ColumnEnrichment
from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.repositories.semantic.enrichment_repository import PostgresEnrichmentRepository


def test_write_then_read_object_enrichment(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("local", "enrichment_test")
    repo = PostgresEnrichmentRepository(migrated_engine)
    enrichment = ObjectEnrichment(
        datasource_name="local",
        schema_name="enrichment_test",
        object_name="orders",
        description="Customer orders.",
        embedding=tuple(0.1 for _ in range(1536)),
    )

    repo.write_object_enrichment(enrichment)
    read_back = repo.read_object_enrichments("local")

    assert any(e.object_name == "orders" and e.description == "Customer orders." for e in read_back)


def test_writing_the_same_object_twice_upserts(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("local", "enrichment_upsert_test")
    repo = PostgresEnrichmentRepository(migrated_engine)
    first = ObjectEnrichment(
        datasource_name="local",
        schema_name="enrichment_upsert_test",
        object_name="orders",
        description="v1",
    )
    repo.write_object_enrichment(first)

    repo.write_object_enrichment(ObjectEnrichment(**{**first.model_dump(), "description": "v2"}))

    read_back = [
        e
        for e in repo.read_object_enrichments("local")
        if e.schema_name == "enrichment_upsert_test"
    ]
    assert len(read_back) == 1
    assert read_back[0].description == "v2"


def test_write_then_read_column_enrichments(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("local", "column_enrichment_test")
    repo = PostgresEnrichmentRepository(migrated_engine)
    column = ColumnEnrichment(
        datasource_name="local",
        schema_name="column_enrichment_test",
        object_name="orders",
        column_name="status",
        description="Order lifecycle state.",
        unit=None,
    )

    written = repo.write_column_enrichments([column])
    read_back = repo.read_column_enrichments(
        SchemaRef(datasource_name="local", schema_name="column_enrichment_test")
    )

    assert written == 1
    assert read_back[0].description == "Order lifecycle state."
