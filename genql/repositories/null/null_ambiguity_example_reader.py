from __future__ import annotations

from genql.domain.entities.ambiguity_example import AmbiguityExample


class NullAmbiguityExampleReader:
    """AmbiguityExampleReader that has nothing to retrieve."""

    def search(
        self, question: str, domain_id: int | None, top_k: int
    ) -> tuple[AmbiguityExample, ...]:
        return ()
