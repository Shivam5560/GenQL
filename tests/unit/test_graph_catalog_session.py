"""The projected graph is always dropped, even when the body raises."""

from __future__ import annotations

from typing import Any

import pytest

from genql.infrastructure.graph.graph_catalog_session import GraphCatalogSession


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


class FakeGraphNamespace:
    def __init__(self, projector: FakeCypherProjector) -> None:
        self.project = projector


class FakeGds:
    def __init__(self, projector: FakeCypherProjector) -> None:
        self.graph = FakeGraphNamespace(projector)


class FakeGdsProvider:
    def __init__(self, gds: FakeGds) -> None:
        self._gds = gds

    def client(self) -> FakeGds:
        return self._gds


def test_the_projection_is_dropped_after_normal_use() -> None:
    graph = FakeGraph()
    provider = FakeGdsProvider(FakeGds(FakeCypherProjector(graph)))

    with GraphCatalogSession(provider, "local") as session_graph:  # type: ignore[arg-type]
        assert session_graph is graph

    assert graph.dropped is True


def test_the_projection_is_dropped_even_if_the_body_raises() -> None:
    graph = FakeGraph()
    provider = FakeGdsProvider(FakeGds(FakeCypherProjector(graph)))

    with pytest.raises(ValueError), GraphCatalogSession(provider, "local"):  # type: ignore[arg-type]
        raise ValueError("boom")

    assert graph.dropped is True


def test_the_graph_name_and_parameters_are_scoped_to_the_datasource() -> None:
    graph = FakeGraph()
    projector = FakeCypherProjector(graph)
    provider = FakeGdsProvider(FakeGds(projector))

    with GraphCatalogSession(provider, "wh2"):  # type: ignore[arg-type]
        pass

    assert projector.calls[0]["name"] == "graph_wh2"
    assert projector.calls[0]["parameters"] == {"datasource_name": "wh2"}


def test_the_relationship_query_returns_every_edge_in_both_directions() -> None:
    """The legacy `gds.graph.project.cypher` procedure projects each
    returned (source, target) row as a directed edge regardless of how the
    Cypher pattern was written — an undirected MATCH pattern alone does not
    produce an undirected projection, since it still returns one row per
    relationship. Leiden (undefined on directed graphs) and join-path mining
    (must reach dim2 from dim1 through a shared fact table) both need the
    edge set to be symmetric, so the query must return each edge as both
    (s, t) and (t, s) via UNION ALL."""
    graph = FakeGraph()
    projector = FakeCypherProjector(graph)
    provider = FakeGdsProvider(FakeGds(projector))

    with GraphCatalogSession(provider, "wh2"):  # type: ignore[arg-type]
        pass

    relationship_query = projector.calls[0]["relationship_query"]
    assert "UNION ALL" in relationship_query
    assert relationship_query.count("->") == 2
    assert "RETURN id(s) AS source, id(t) AS target" in relationship_query
    assert "RETURN id(t) AS source, id(s) AS target" in relationship_query
