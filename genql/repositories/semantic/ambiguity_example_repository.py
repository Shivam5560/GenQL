"""The offline synthetic ambiguity log's reader and writer.

Both embed internally via an injected EmbeddingProvider (Deviation 4): the
AmbiguityExampleReader/Writer ports carry no embedding parameter, unlike
Retriever.search, which receives one pre-computed by RetrievalService. The
read shape otherwise mirrors DenseRetriever's cosine-distance ORDER BY LIMIT
exactly, applied to this smaller table.

A domain-scoped search also returns unscoped (`domain_id IS NULL`) rows: 0008's
ON DELETE SET NULL keeps an orphaned example as a valid general exemplar, so
excluding those rows would quietly discard the log's cross-domain half.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.domain.ports.embedding_provider import EmbeddingProvider

_SEARCH = text("""
    SELECT question, interpretations, resolution, domain_id
    FROM genql.genql_ambiguity_example
    WHERE (CAST(:domain_id AS bigint) IS NULL OR domain_id = :domain_id OR domain_id IS NULL)
    ORDER BY embedding <=> CAST(:query_embedding AS vector)
    LIMIT :top_k
""")

_INSERT = text("""
    INSERT INTO genql.genql_ambiguity_example
        (domain_id, question, interpretations, resolution, embedding)
    VALUES (:domain_id, :question, :interpretations, :resolution, :embedding)
""")


class PostgresAmbiguityExampleReader:
    def __init__(self, engine: Engine, embedder: EmbeddingProvider) -> None:
        self._engine = engine
        self._embedder = embedder

    def search(
        self, question: str, domain_id: int | None, top_k: int
    ) -> tuple[AmbiguityExample, ...]:
        query_embedding = self._embedder.embed([question])[0]
        with self._engine.connect() as conn:
            rows = conn.execute(
                _SEARCH,
                {
                    "domain_id": domain_id,
                    "query_embedding": str(list(query_embedding)),
                    "top_k": top_k,
                },
            ).all()
        return tuple(
            AmbiguityExample(
                question=row.question,
                interpretations=tuple(row.interpretations),
                resolution=row.resolution,
                domain_id=row.domain_id,
            )
            for row in rows
        )


class PostgresAmbiguityExampleWriter:
    def __init__(self, engine: Engine, embedder: EmbeddingProvider) -> None:
        self._engine = engine
        self._embedder = embedder

    def write(self, examples: Sequence[AmbiguityExample]) -> None:
        if not examples:
            return
        embeddings = self._embedder.embed([e.question for e in examples])
        rows = [
            {
                "domain_id": example.domain_id,
                "question": example.question,
                "interpretations": list(example.interpretations),
                "resolution": example.resolution,
                "embedding": list(embedding),
            }
            for example, embedding in zip(examples, embeddings, strict=True)
        ]
        with self._engine.begin() as conn:
            conn.execute(_INSERT, rows)
