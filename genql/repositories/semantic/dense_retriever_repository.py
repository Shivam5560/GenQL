"""pgvector cosine-distance ranking, converted to a similarity score
(1 - distance) so higher is better everywhere, matching Bm25Retriever's
scoring direction."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.ports.retriever import SearchResult
from genql.repositories.semantic.registry import RETRIEVERS

_SEARCH = text("""
    SELECT datasource_name, schema_name, object_name, domain_name,
           1 - (embedding <=> CAST(:query_embedding AS vector)) AS score
    FROM genql.genql_search_document
    WHERE datasource_name = :datasource_name
      AND (CAST(:domain_id AS bigint) IS NULL OR (schema_name, object_name) IN (
            SELECT schema_name, object_name FROM genql.genql_domain_member
            WHERE domain_id = :domain_id
          ))
    ORDER BY embedding <=> CAST(:query_embedding AS vector)
    LIMIT :top_k
""")


@RETRIEVERS.register("dense")
class DenseRetriever:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def search(
        self,
        datasource_name: str,
        query: str,
        query_embedding: Sequence[float],
        top_k: int,
        domain_id: int | None = None,
    ) -> Sequence[SearchResult]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                _SEARCH,
                {
                    "datasource_name": datasource_name,
                    "query_embedding": str(list(query_embedding)),
                    "top_k": top_k,
                    "domain_id": domain_id,
                },
            ).all()
        return [SearchResult.model_validate(r._mapping) for r in rows]  # noqa: SLF001
