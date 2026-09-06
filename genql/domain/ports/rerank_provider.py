from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict


class RerankScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    index: int
    score: float


@runtime_checkable
class RerankProvider(Protocol):
    def rerank(self, query: str, documents: Sequence[str], top_n: int) -> Sequence[RerankScore]: ...
