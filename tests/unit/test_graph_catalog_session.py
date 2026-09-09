"""The projected graph is always dropped, even when the body raises, and is
always mutated into an undirected relationship type before being handed to
the caller."""

from __future__ import annotations

from typing import Any

import pytest

from genql.infrastructure.graph.graph_catalog_session import (
    UNDIRECTED_RELATIONSHIP_TYPE,
    GraphCatalogSession,
)


class FakeGraph:
    def __init__(self) -> None:
        self.dropped = False

    def drop(self) -> None:
        self.dropped = True


class FakeCypherProjector:
    def __init__(self, graph: FakeGraph) -> None:
        self._graph = graph
        self.calls: list[dict[str, Any]] = []

    def cypher(self, name: str, node_query: str, relationship_query: str, **kwargs: Any) -> tuple:
        self.calls.append(
            {
                "name": name,
                "parameters": kwargs.get("parameters"),
                "relationship_query": relationship_query,
            }
        )
        return self._graph, None


class FakeToUndirected:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, graph: FakeGraph, **kwargs: Any) -> None:
        self.calls.append({"graph": graph, **kwargs})


class FakeRelationshipsNamespace:
    def __init__(self, to_undirected: FakeToUndirected) -> None:
        self.toUndirected = to_undirected


class FakeGraphNamespace:
    def __init__(self, projector: FakeCypherProjector, to_undirected: FakeToUndirected) -> None:
        self.project = projector
        self.relationships = FakeRelationshipsNamespace(to_undirected)


class FakeGds:
    def __init__(self, projector: FakeCypherProjector, to_undirected: FakeToUndirected) -> None:
        self.graph = FakeGraphNamespace(projector, to_undirected)


class FakeGdsProvider:
    def __init__(self, gds: FakeGds) -> None:
        self._gds = gds

    def client(self) -> FakeGds:
        return self._gds


def _provider(graph: FakeGraph) -> tuple[FakeGdsProvider, FakeCypherProjector, FakeToUndirected]:
    projector = FakeCypherProjector(graph)
    to_undirected = FakeToUndirected()
    return FakeGdsProvider(FakeGds(projector, to_undirected)), projector, to_undirected


def test_the_projection_is_dropped_after_normal_use() -> None:
    graph = FakeGraph()
    provider, _, _ = _provider(graph)

    with GraphCatalogSession(provider, "local") as session_graph:  # type: ignore[arg-type]
        assert session_graph is graph

    assert graph.dropped is True


def test_the_projection_is_dropped_even_if_the_body_raises() -> None:
    graph = FakeGraph()
    provider, _, _ = _provider(graph)

    with pytest.raises(ValueError), GraphCatalogSession(provider, "local"):  # type: ignore[arg-type]
        raise ValueError("boom")

    assert graph.dropped is True


def test_the_graph_name_and_parameters_are_scoped_to_the_datasource() -> None:
    graph = FakeGraph()
    provider, projector, _ = _provider(graph)

    with GraphCatalogSession(provider, "wh2"):  # type: ignore[arg-type]
        pass

    assert projector.calls[0]["name"] == "graph_wh2"
    assert projector.calls[0]["parameters"] == {"datasource_name": "wh2"}


def test_the_relationship_query_is_directed_fk_edges() -> None:
    """The legacy `gds.graph.project.cypher` procedure always marks its
    projected relationship set as directed regardless of how the Cypher
    pattern is written, so the query just states the real FK direction —
    undirected traversal is produced separately via `toUndirected`, not by
    how this query is phrased."""
    graph = FakeGraph()
    provider, projector, _ = _provider(graph)

    with GraphCatalogSession(provider, "wh2"):  # type: ignore[arg-type]
        pass

    relationship_query = projector.calls[0]["relationship_query"]
    assert "-[:REFERENCES]->" in relationship_query
    assert "UNION" not in relationship_query


def test_the_projection_is_mutated_into_an_undirected_relationship_type() -> None:
    graph = FakeGraph()
    provider, _, to_undirected = _provider(graph)

    with GraphCatalogSession(provider, "wh2"):  # type: ignore[arg-type]
        pass

    assert len(to_undirected.calls) == 1
    call = to_undirected.calls[0]
    assert call["graph"] is graph
    assert call["relationship_type"] == "__ALL__"
    assert call["mutate_relationship_type"] == UNDIRECTED_RELATIONSHIP_TYPE
