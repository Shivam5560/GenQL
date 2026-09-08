"""pg_search BM25 ranking over genql_search_document.content."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.ports.retriever import SearchResult
from genql.repositories.semantic.registry import RETRIEVERS

_SEARCH = text("""
    SELECT datasource_name, schema_name, object_name, domain_name, paradedb.score(id) AS score
    FROM genql.genql_search_document
    WHERE datasource_name = :datasource_name AND content @@@ :query
      AND (CAST(:domain_id AS bigint) IS NULL OR (schema_name, object_name) IN (
            SELECT schema_name, object_name FROM genql.genql_domain_member
            WHERE domain_id = :domain_id
          ))
    ORDER BY score DESC
    LIMIT :top_k
""")


@RETRIEVERS.register("bm25")
class Bm25Retriever:
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
                    "query": query,
                    "top_k": top_k,
                    "domain_id": domain_id,
                },
            ).all()
        return [SearchResult.model_validate(r._mapping) for r in rows]  # noqa: SLF001
