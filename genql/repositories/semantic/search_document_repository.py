"""Builds one genql_search_document row per object: name, type, description,
alias, domain name, and each column's name, description, unit, and sample
values — the exact field list the parent spec names for the BM25 text.
Embeds the assembled text and upserts."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from sqlalchemy import Engine, Row, text

from genql.domain.errors import CompileError, EmbeddingProviderError
from genql.domain.ports.embedding_provider import EmbeddingProvider

_SELECT_OBJECTS = text("""
    SELECT o.schema_name, o.object_name, o.object_type, oe.description, oe.business_alias,
           d.name AS domain_name
    FROM genql.genql_object o
    JOIN genql.genql_schema s
        ON s.datasource_name = o.datasource_name AND s.schema_name = o.schema_name
    LEFT JOIN genql.genql_object_enrichment oe
        ON oe.datasource_name = o.datasource_name AND oe.schema_name = o.schema_name
        AND oe.object_name = o.object_name
    LEFT JOIN genql.genql_domain_member dm
        ON dm.datasource_name = o.datasource_name AND dm.schema_name = o.schema_name
        AND dm.object_name = o.object_name
    LEFT JOIN genql.genql_domain d ON d.id = dm.domain_id
    WHERE o.datasource_name = :datasource_name AND s.enabled
""")

_SELECT_COLUMNS = text("""
    SELECT c.schema_name, c.object_name, c.column_name, ce.description, ce.unit,
           cp.sample_values
    FROM genql.genql_column c
    LEFT JOIN genql.genql_column_enrichment ce
        ON ce.datasource_name = c.datasource_name AND ce.schema_name = c.schema_name
        AND ce.object_name = c.object_name AND ce.column_name = c.column_name
    LEFT JOIN genql.genql_column_profile cp
        ON cp.datasource_name = c.datasource_name AND cp.schema_name = c.schema_name
        AND cp.object_name = c.object_name AND cp.column_name = c.column_name
    WHERE c.datasource_name = :datasource_name
""")

_UPSERT_DOCUMENT = text("""
    INSERT INTO genql.genql_search_document
        (datasource_name, schema_name, object_name, domain_name, content, embedding)
    VALUES (:datasource_name, :schema_name, :object_name, :domain_name, :content, :embedding)
    ON CONFLICT ON CONSTRAINT uq_genql_search_document_identity DO UPDATE
        SET domain_name = EXCLUDED.domain_name,
            content = EXCLUDED.content,
            embedding = EXCLUDED.embedding,
            updated_at = now()
""")


def _content_for(  # noqa: PLR0913, PLR0917 - one field per BM25/embedding content component
    *,
    object_name: str,
    object_type: str,
    domain_name: str,
    description: str | None,
    business_alias: str | None,
    columns: Sequence[tuple[str, str | None, str | None, Sequence[str] | None]],
    include_enrichment: bool,
) -> str:
    """Assemble one object's BM25/embedding text.

    `columns` is a sequence of `(column_name, description, unit, sample_values)`
    tuples. When `include_enrichment` is false, the object description, the
    business alias, and each column's description and unit are omitted —
    everything an LLM wrote. Column names and profiled sample values stay:
    they come from structure and data profiling, not from enrichment.
    """
    column_lines = [
        f"{col_name}: {(col_description or '') if include_enrichment else ''} "
        f"(unit: {(col_unit or 'n/a') if include_enrichment else 'n/a'}; "
        f"samples: {list(sample_values or [])})"
        for col_name, col_description, col_unit, sample_values in columns
    ]
    description_text = (description or "") if include_enrichment else ""
    alias_text = (business_alias or "n/a") if include_enrichment else "n/a"
    return (
        f"{object_name} ({object_type}) in domain {domain_name}. "
        f"{description_text} Also known as: {alias_text}. "
        f"Columns: {'; '.join(column_lines)}"
    )


class SearchDocumentCompiler:
    """Compiles genql_search_document rows from object and column metadata.

    `include_enrichment` exists for the ablation harness (the `no_descriptions`
    ablation) and is never set from the environment — every real construction
    site leaves it at its default of `True`.
    """

    def __init__(
        self, engine: Engine, embedder: EmbeddingProvider, include_enrichment: bool = True
    ) -> None:
        self._engine = engine
        self._embedder = embedder
        self._include_enrichment = include_enrichment

    def compile(self, datasource_name: str) -> int:
        with self._engine.connect() as conn:
            object_rows = conn.execute(_SELECT_OBJECTS, {"datasource_name": datasource_name}).all()
            column_rows = conn.execute(_SELECT_COLUMNS, {"datasource_name": datasource_name}).all()
        if not object_rows:
            return 0

        columns_by_object: dict[tuple[str, str], list[Row[Any]]] = {}
        for row in column_rows:
            columns_by_object.setdefault((row.schema_name, row.object_name), []).append(row)

        contents: list[str] = []
        keys: list[tuple[str, str, str | None]] = []
        for row in object_rows:
            domain_name = row.domain_name or "unassigned"
            contents.append(
                _content_for(
                    object_name=row.object_name,
                    object_type=row.object_type,
                    domain_name=domain_name,
                    description=row.description,
                    business_alias=row.business_alias,
                    columns=[
                        (col.column_name, col.description, col.unit, col.sample_values)
                        for col in columns_by_object.get((row.schema_name, row.object_name), [])
                    ],
                    include_enrichment=self._include_enrichment,
                )
            )
            keys.append((row.schema_name, row.object_name, row.domain_name))

        try:
            embeddings = self._embedder.embed(contents)
        except EmbeddingProviderError as exc:
            raise CompileError(
                f"failed to embed search documents for {datasource_name!r}: {exc}"
            ) from exc

        rows = [
            {
                "datasource_name": datasource_name,
                "schema_name": schema_name,
                "object_name": object_name,
                "domain_name": domain_name,
                "content": content,
                "embedding": list(embedding),
            }
            for (schema_name, object_name, domain_name), content, embedding in zip(
                keys, contents, embeddings, strict=True
            )
        ]
        with self._engine.begin() as conn:
            conn.execute(_UPSERT_DOCUMENT, rows)
        return len(rows)
