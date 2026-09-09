"""Ranks index recommendations for the operator who will act on them.

A service for one line of sorting, rather than the CLI calling the port
directly, because "controllers hold no business logic" is a rule the codebase
keeps without exception — and because the tie-break is a real decision: equal
evidence sorts by column name so that two runs over the same data print the
same order.
"""

from __future__ import annotations

from genql.domain.entities.index_recommendation import IndexRecommendation
from genql.domain.ports.index_recommender import IndexRecommender


class IndexRecommendationService:
    def __init__(self, recommender: IndexRecommender) -> None:
        self._recommender = recommender

    def recommend(self, datasource_name: str) -> tuple[IndexRecommendation, ...]:
        return tuple(
            sorted(
                self._recommender.recommend(datasource_name),
                key=lambda r: (-r.supporting_execution_count, r.column_name),
            )
        )
