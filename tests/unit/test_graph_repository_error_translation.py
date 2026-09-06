"""A raw Neo4j/GDS driver failure must reach the caller as a typed domain
error at the repository boundary.

This matters because GraphProjectionStep only catches DiscoveryError and
DiscoveryRunner only catches GenqlError, and `genql graph analyze`/`rebuild`
only catch GenqlError — an untranslated driver exception would be an
unhandled traceback instead of a failed step or a "message + exit 1" CLI
result. GraphProjectionError and GraphAnalysisError are both subclasses of
those bases, so translating at the repository is enough for both callers.
"""

from __future__ import annotations

from typing import Any

import pytest
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from genql.domain.entities.database_object import DatabaseObject
from genql.domain.errors import GraphAnalysisError, GraphProjectionError
from genql.domain.value_objects.object_type import ObjectType
from genql.repositories.graph.clustering_algorithm_repository import LeidenClusteringAlgorithm
from genql.repositories.graph.graph_writer_repository import Neo4jGraphWriterRepository
from genql.repositories.graph.join_path_miner_repository import WeightedShortestPathJoinPathMiner
from genql.repositories.graph.node_embedder_repository import FastRpNodeEmbedder


class _RaisingSession:
    def __enter__(self) -> _RaisingSession:
        return self

    def __exit__(self, *exc_info: Any) -> None:
        return None

    def run(self, *args: Any, **kwargs: Any) -> Any:
        raise ServiceUnavailable("connection refused")


class _RaisingDriver:
    def session(self) -> _RaisingSession:
        return _RaisingSession()


class _RaisingCypherProjector:
    def cypher(self, *args: Any, **kwargs: Any) -> Any:
        raise Neo4jError("no procedure with the name `gds.graph.project.cypher` succeeded")


class _RaisingGraphNamespace:
    def __init__(self) -> None:
        self.project = _RaisingCypherProjector()


class _RaisingGds:
    def __init__(self) -> None:
        self.graph = _RaisingGraphNamespace()


class _RaisingGdsProvider:
    def client(self) -> _RaisingGds:
        return _RaisingGds()


def test_graph_writer_translates_a_driver_failure_into_graph_projection_error() -> None:
    repo = Neo4jGraphWriterRepository(_RaisingDriver())  # type: ignore[arg-type]
    obj = DatabaseObject(
        datasource_name="ds", schema_name="s", object_name="t", object_type=ObjectType.TABLE
    )

    with pytest.raises(GraphProjectionError):
        repo.write_objects([obj])


def test_leiden_translates_a_driver_failure_into_graph_analysis_error() -> None:
    algo = LeidenClusteringAlgorithm(_RaisingGdsProvider())  # type: ignore[arg-type]

    with pytest.raises(GraphAnalysisError):
        algo.detect("ds")


def test_fastrp_translates_a_driver_failure_into_graph_analysis_error() -> None:
    embedder = FastRpNodeEmbedder(_RaisingGdsProvider())  # type: ignore[arg-type]

    with pytest.raises(GraphAnalysisError):
        embedder.embed("ds")


def test_join_path_miner_translates_a_driver_failure_into_graph_analysis_error() -> None:
    miner = WeightedShortestPathJoinPathMiner(_RaisingDriver(), _RaisingGdsProvider())  # type: ignore[arg-type]

    with pytest.raises(GraphAnalysisError):
        miner.mine("ds")
