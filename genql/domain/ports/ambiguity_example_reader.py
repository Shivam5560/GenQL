from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.ambiguity_example import AmbiguityExample


@runtime_checkable
class AmbiguityExampleReader(Protocol):
    def search(
        self, question: str, domain_id: int | None, top_k: int
    ) -> tuple[AmbiguityExample, ...]: ...
