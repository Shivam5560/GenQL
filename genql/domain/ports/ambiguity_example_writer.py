from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.ambiguity_example import AmbiguityExample


@runtime_checkable
class AmbiguityExampleWriter(Protocol):
    def write(self, examples: tuple[AmbiguityExample, ...]) -> None: ...
