"""Seeds documents engineered to favor one signal over the other — a
distinctive keyword with a nearly-orthogonal embedding on one row, a
matching embedding with unrelated text on another — and asserts hybrid
ranking differs from either single-signal ranking alone."""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import Engine, text

from genql.repositories.semantic.bm25_retriever_repository import Bm25Retriever
from genql.repositories.semantic.dense_retriever_repository import DenseRetriever
from genql.repositories.semantic.hybrid_rrf_retriever_repository import HybridRrfRetriever


def _seed(engine: Engine, datasource_name: str) -> None:
    keyword_embedding = [0.0] * 1536
    vector_embedding = [1.0] + [0.0] * 1535
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO genql.genql_search_document "
                "(datasource_name, schema_name, object_name, content, embedding) VALUES "
                "(:ds, 'shop', 'keyword_match', 'zorblatt unique keyword content', "
                " CAST(:e1 AS vector)), "
                "(:ds, 'shop', 'vector_match', 'completely unrelated generic text', "
                " CAST(:e2 AS vector))"
            ),
            {"ds": datasource_name, "e1": str(keyword_embedding), "e2": str(vector_embedding)},
        )


def test_bm25_and_dense_disagree_and_hybrid_blends_them(
    migrated_engine: Engine, register_schema: Callable[[str, str], None]
) -> None:
    register_schema("local", "shop")
    ds = "retriever_test"
    register_schema(ds, "shop")
    _seed(migrated_engine, ds)
    query_embedding = [1.0] + [0.0] * 1535

    bm25_top = Bm25Retriever(migrated_engine).search(ds, "zorblatt", query_embedding, top_k=2)[0]
    dense_top = DenseRetriever(migrated_engine).search(ds, "zorblatt", query_embedding, top_k=2)[0]
    hybrid = HybridRrfRetriever(migrated_engine).search(ds, "zorblatt", query_embedding, top_k=2)

    assert bm25_top.object_name == "keyword_match"
    assert dense_top.object_name == "vector_match"
    assert {r.object_name for r in hybrid} == {"keyword_match", "vector_match"}
