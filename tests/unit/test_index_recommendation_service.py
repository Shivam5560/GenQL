"""One line of logic, and it is the ordering an operator reads top-down."""

from __future__ import annotations

from genql.domain.entities.index_recommendation import IndexRecommendation
from genql.services.query.index_recommendation_service import IndexRecommendationService


def _rec(column: str, count: int) -> IndexRecommendation:
    return IndexRecommendation(
        object_qualified_name="local.tpcds.store_sales",
        column_name=column,
        rationale="r",
        supporting_execution_count=count,
    )


class _Recommender:
    def __init__(self, *recs: IndexRecommendation) -> None:
        self._recs = recs

    def recommend(self, datasource_name: str) -> tuple[IndexRecommendation, ...]:
        return self._recs


def test_recommendations_are_ranked_by_supporting_evidence_descending() -> None:
    service = IndexRecommendationService(_Recommender(_rec("a", 2), _rec("b", 9), _rec("c", 5)))

    assert [r.column_name for r in service.recommend("local")] == ["b", "c", "a"]


def test_ties_are_broken_by_column_name_so_output_is_stable() -> None:
    service = IndexRecommendationService(_Recommender(_rec("z", 3), _rec("a", 3)))

    assert [r.column_name for r in service.recommend("local")] == ["a", "z"]


def test_no_evidence_yields_no_recommendations() -> None:
    assert IndexRecommendationService(_Recommender()).recommend("local") == ()
