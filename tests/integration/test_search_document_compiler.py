"""Uses a fake EmbeddingProvider — this test proves the SQL and the content
assembly, not embedding quality, which the gated OpenRouter tests already
cover."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from sqlalchemy import Engine, text

from genql.repositories.semantic.search_document_repository import SearchDocumentCompiler


class FakeEmbeddingProvider:
    def embed(self, texts: Sequence[str]) -> Sequence[tuple[float, ...]]:
        return [tuple([0.0] * 1536) for _ in texts]


def test_compile_writes_one_document_per_object(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("local", "compile_test")
    with migrated_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO genql.genql_object (datasource_name, schema_name, object_name, "
                "object_type) VALUES ('local', 'compile_test', 'orders', 'table')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO genql.genql_object_enrichment "
                "(datasource_name, schema_name, object_name, description) "
                "VALUES ('local', 'compile_test', 'orders', 'Customer orders.')"
            )
        )

    written = SearchDocumentCompiler(migrated_engine, FakeEmbeddingProvider()).compile("local")

    assert written >= 1
    with migrated_engine.connect() as conn:
        content = conn.execute(
            text(
                "SELECT content FROM genql.genql_search_document "
                "WHERE datasource_name = 'local' AND schema_name = 'compile_test' "
                "AND object_name = 'orders'"
            )
        ).scalar_one()
    assert "Customer orders." in content
