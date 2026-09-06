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
        self.calls.append({"name": name, "parameters": kwargs.get("parameters")})
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
