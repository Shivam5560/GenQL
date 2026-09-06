from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DomainScoper(Protocol):
    """Stage 3. Best-effort: returns None rather than raising when no domain
    can be resolved, because an unscoped retrieval is a correct fallback and a
    hard failure here would break questions that simply span domains."""

    def resolve(self, question: str, datasource_name: str) -> int | None: ...
