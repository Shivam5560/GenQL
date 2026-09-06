"""The parent spec's 'single SQL statement': two ranked CTEs, one BM25, one
vector-distance, combined by reciprocal rank fusion — fusion happens in the
database, not by round-tripping two result sets through Python."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.ports.retriever import SearchResult
from genql.repositories.semantic.registry import RETRIEVERS

_SEARCH = text("""
    WITH bm25_ranked AS (
        SELECT id, datasource_name, schema_name, object_name, domain_name,
               ROW_NUMBER() OVER (ORDER BY paradedb.score(id) DESC) AS rank
        FROM genql.genql_search_document
        WHERE datasource_name = :datasource_name AND content @@@ :query
    ),
    dense_ranked AS (
        SELECT id, datasource_name, schema_name, object_name, domain_name,
               ROW_NUMBER() OVER (ORDER BY embedding <=> CAST(:query_embedding AS vector)) AS rank
        FROM genql.genql_search_document
        WHERE datasource_name = :datasource_name
    )
    SELECT
        COALESCE(b.datasource_name, d.datasource_name) AS datasource_name,
        COALESCE(b.schema_name, d.schema_name) AS schema_name,
        COALESCE(b.object_name, d.object_name) AS object_name,
        COALESCE(b.domain_name, d.domain_name) AS domain_name,
        (COALESCE(1.0 / (:rrf_k + b.rank), 0) + COALESCE(1.0 / (:rrf_k + d.rank), 0)) AS score
    FROM bm25_ranked b
    FULL OUTER JOIN dense_ranked d ON b.id = d.id
    WHERE (:domain_id::bigint IS NULL OR (COALESCE(b.schema_name, d.schema_name),
           COALESCE(b.object_name, d.object_name)) IN (
        SELECT schema_name, object_name FROM genql.genql_domain_member WHERE domain_id = :domain_id
    ))
    ORDER BY score DESC
    LIMIT :top_k
""")


@RETRIEVERS.register("hybrid_rrf")
class HybridRrfRetriever:
    def __init__(self, engine: Engine, rrf_k: int = 60) -> None:
        self._engine = engine
        self._rrf_k = rrf_k

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
                    "query_embedding": str(list(query_embedding)),
                    "top_k": top_k,
                    "domain_id": domain_id,
                    "rrf_k": self._rrf_k,
                },
            ).all()
        return [SearchResult.model_validate(r._mapping) for r in rows]  # noqa: SLF001
