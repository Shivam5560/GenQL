"""Reads accumulated rewrite outcomes and proposes indexes for a human."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.index_recommendation import IndexRecommendation


@runtime_checkable
class IndexRecommender(Protocol):
    def recommend(self, datasource_name: str) -> tuple[IndexRecommendation, ...]: ...
