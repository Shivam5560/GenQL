"""Runs clustering, then embedding, then join-path mining, and persists the
mined paths. All four dependencies are ports, so no database or Neo4j is
needed here."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.join_path import JoinPath
from genql.services.graph.graph_analysis_service import GraphAnalysisService

PATH = JoinPath(
    datasource_name="local",
    schema_name="shop",
    source_object="a",
    target_object="c",
    path=("a", "b", "c"),
    weight=2.0,
)


class FakeClustering:
    def detect(self, datasource_name: str) -> int:
        return 3


class FakeEmbedder:
    def embed(self, datasource_name: str) -> int:
        return 7


class FakeMiner:
    def mine(self, datasource_name: str) -> Sequence[JoinPath]:
        return [PATH]


class FakeJoinPathWriter:
    def __init__(self) -> None:
        self.written: list[JoinPath] = []

    def write(self, paths: Sequence[JoinPath]) -> int:
        self.written.extend(paths)
        return len(paths)


def test_analyze_runs_all_three_algorithms_and_persists_paths() -> None:
    writer = FakeJoinPathWriter()
    service = GraphAnalysisService(FakeClustering(), FakeEmbedder(), FakeMiner(), writer)

    report = service.analyze("local")

    assert report.communities == 3
    assert report.embedded_nodes == 7
    assert report.join_paths == 1
    assert writer.written == [PATH]
