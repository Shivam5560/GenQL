"""Stage 3, against a fake RetrievalService and a fake DomainReader.

This is deliberately a best-effort heuristic, so the tests pin the shape of the
heuristic rather than its accuracy: an unscoped sample, a plurality vote over
domain_name, a name-to-id lookup, and None wherever any of the three has
nothing to work with. Getting the domain WRONG is a documented risk (spec §11)
that --domain-id overrides; getting it wrong SILENTLY and irreversibly is what
these tests exist to prevent.
"""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from genql.domain.errors import DomainScopingError, RetrievalError
from genql.domain.ports.retriever import SearchResult
from genql.services.query.domain_scoping_service import DomainScopingService


def hit(domain_name: str | None, object_name: str = "t", score: float = 1.0) -> SearchResult:
    return SearchResult(
        datasource_name="local",
        schema_name="tpcds",
        object_name=object_name,
        domain_name=domain_name,
        score=score,
    )


class FakeRetrieval:
    def __init__(self, results: Sequence[SearchResult]) -> None:
        self.results = list(results)
        self.calls: list[tuple[str, str, int, int | None]] = []

    def search(
        self, datasource_name: str, query: str, top_k: int, domain_id: int | None = None
    ) -> Sequence[SearchResult]:
        self.calls.append((datasource_name, query, top_k, domain_id))
        return self.results


class RaisingRetrieval:
    def search(
        self, datasource_name: str, query: str, top_k: int, domain_id: int | None = None
    ) -> Sequence[SearchResult]:
        raise RetrievalError("index unavailable")


class FakeDomains:
    def __init__(self, ids: dict[str, int] | None = None) -> None:
        self.ids = ids or {}
        self.looked_up: list[tuple[str, str]] = []

    def domain_id_by_name(self, datasource_name: str, name: str) -> int | None:
        self.looked_up.append((datasource_name, name))
        return self.ids.get(name)


def service(
    results: Sequence[SearchResult], ids: dict[str, int] | None = None, sample_size: int = 20
) -> tuple[DomainScopingService, FakeRetrieval, FakeDomains]:
    retrieval = FakeRetrieval(results)
    domains = FakeDomains(ids)
    return (
        DomainScopingService(retrieval, domains, sample_size),  # type: ignore[arg-type]
        retrieval,
        domains,
    )


def test_the_plurality_domain_is_resolved_to_its_id() -> None:
    scoper, _, domains = service(
        [hit("Sales"), hit("Sales"), hit("Inventory")], ids={"Sales": 3, "Inventory": 9}
    )

    assert scoper.resolve("q", "local") == 3
    assert domains.looked_up == [("local", "Sales")]


def test_the_sample_is_unscoped_and_sized_from_settings() -> None:
    """The first real caller of the unscoped pass: scoping cannot pass a
    domain_id, because resolving one is the whole point of this stage."""
    scoper, retrieval, _ = service([hit("Sales")], ids={"Sales": 3}, sample_size=25)

    scoper.resolve("how much did we sell", "local")

    assert retrieval.calls == [("local", "how much did we sell", 25, None)]


def test_an_empty_sample_resolves_to_none_without_a_lookup() -> None:
    scoper, _, domains = service([])

    assert scoper.resolve("q", "local") is None
    assert domains.looked_up == []


def test_hits_with_no_domain_are_ignored() -> None:
    scoper, _, _ = service([hit(None), hit(None), hit("Sales")], ids={"Sales": 3})

    assert scoper.resolve("q", "local") == 3


def test_a_sample_where_every_hit_lacks_a_domain_resolves_to_none() -> None:
    scoper, _, domains = service([hit(None), hit(None)])

    assert scoper.resolve("q", "local") is None
    assert domains.looked_up == []


def test_a_tie_is_broken_by_the_highest_ranked_hit() -> None:
    """Counter.most_common preserves insertion order on ties, and retrieval
    returns hits already ranked, so the tie-break is "whichever domain the best
    hit belonged to" — deterministic, and the most defensible answer available
    without adding a confidence model this phase deliberately defers."""
    scoper, _, _ = service([hit("Inventory"), hit("Sales")], ids={"Sales": 3, "Inventory": 9})

    assert scoper.resolve("q", "local") == 9


def test_a_domain_name_that_no_longer_resolves_yields_none() -> None:
    """A stale search index is not a broken query: fall back to unscoped."""
    scoper, _, _ = service([hit("Retired Domain")], ids={})

    assert scoper.resolve("q", "local") is None


def test_a_retrieval_failure_becomes_a_domain_scoping_error() -> None:
    scoper = DomainScopingService(RaisingRetrieval(), FakeDomains(), 20)  # type: ignore[arg-type]

    with pytest.raises(DomainScopingError):
        scoper.resolve("q", "local")
