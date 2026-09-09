"""The ordering an operator reads top-down, and the one refusal: a name that
was never registered is a typo, not an absence of evidence."""

from __future__ import annotations

import pytest

from genql.domain.entities.datasource import Datasource
from genql.domain.entities.index_recommendation import IndexRecommendation
from genql.domain.errors import UnknownDatasourceError
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


class _Datasources:
    """Only `get` is exercised; the rest of the port is inert here."""

    def __init__(self, *known: str) -> None:
        self._known = set(known)

    def add(self, datasource: Datasource) -> None: ...

    def get(self, name: str) -> Datasource:
        if name not in self._known:
            raise UnknownDatasourceError(name, sorted(self._known))
        return Datasource(name=name, dialect="postgres", dsn_env_var="GENQL_WAREHOUSE_DSN")

    def list_all(self, enabled_only: bool = False) -> list[Datasource]:
        return []

    def remove(self, name: str) -> None: ...


def _service(*recs: IndexRecommendation) -> IndexRecommendationService:
    return IndexRecommendationService(_Recommender(*recs), _Datasources("local"))


def test_recommendations_are_ranked_by_supporting_evidence_descending() -> None:
    service = _service(_rec("a", 2), _rec("b", 9), _rec("c", 5))

    assert [r.column_name for r in service.recommend("local")] == ["b", "c", "a"]


def test_ties_are_broken_by_column_name_so_output_is_stable() -> None:
    service = _service(_rec("z", 3), _rec("a", 3))

    assert [r.column_name for r in service.recommend("local")] == ["a", "z"]


def test_no_evidence_yields_no_recommendations() -> None:
    assert _service().recommend("local") == ()


def test_an_unregistered_datasource_is_refused_rather_than_reported_empty() -> None:
    with pytest.raises(UnknownDatasourceError):
        _service(_rec("a", 2)).recommend("nope")
