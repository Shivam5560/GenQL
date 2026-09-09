"""The reader and writer both embed internally (Deviation 4): the domain
ports carry no embedding parameter, so nothing upstream can compute it for
them. FakeEmbeddingProvider returns a fixed vector regardless of input so the
distance ordering below is driven only by which rows exist, not by real
semantic similarity — that is proven separately in the real-provider tests.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from sqlalchemy import Engine, text

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.repositories.semantic.ambiguity_example_repository import (
    PostgresAmbiguityExampleReader,
    PostgresAmbiguityExampleWriter,
)

DS = "ambiguity_example_ds"


class FixedEmbeddingProvider:
    def __init__(self, dim: int = 1536) -> None:
        self._dim = dim

    def embed(self, texts: Sequence[str]) -> Sequence[tuple[float, ...]]:
        return [tuple([0.1] * self._dim) for _ in texts]


@pytest.fixture()
def seeded(migrated_engine: Engine, register_schema: object) -> Engine:
    register_schema(DS, "public")  # type: ignore[operator]
    with migrated_engine.begin() as conn:
        conn.execute(text("DELETE FROM genql.genql_ambiguity_example WHERE domain_id IS NULL"))
    return migrated_engine


def test_a_written_example_is_found_by_search(seeded: Engine) -> None:
    embedder = FixedEmbeddingProvider()
    writer = PostgresAmbiguityExampleWriter(seeded, embedder)
    example = AmbiguityExample(
        question="show me revenue",
        interpretations=("gross revenue", "net revenue"),
        resolution="Net revenue, per the finance glossary.",
        domain_id=None,
    )

    writer.write((example,))
    found = PostgresAmbiguityExampleReader(seeded, embedder).search("revenue", None, 5)

    assert any(e.question == "show me revenue" for e in found)


def test_search_respects_top_k(seeded: Engine) -> None:
    embedder = FixedEmbeddingProvider()
    writer = PostgresAmbiguityExampleWriter(seeded, embedder)
    writer.write(
        tuple(
            AmbiguityExample(question=f"q{i}", interpretations=("a", "b"), resolution="r")
            for i in range(5)
        )
    )

    found = PostgresAmbiguityExampleReader(seeded, embedder).search("q", None, 2)

    assert len(found) == 2


def test_writing_no_examples_is_a_no_op() -> None:
    embedder = FixedEmbeddingProvider()
    # No engine call should happen at all; a None engine would raise if write()
    # tried to open a connection for an empty batch.
    PostgresAmbiguityExampleWriter(engine=None, embedder=embedder).write(())  # type: ignore[arg-type]


def test_search_with_no_rows_returns_empty(seeded: Engine) -> None:
    found = PostgresAmbiguityExampleReader(seeded, FixedEmbeddingProvider()).search(
        "nothing", None, 5
    )

    assert found == ()
