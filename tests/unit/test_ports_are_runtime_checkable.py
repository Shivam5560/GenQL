"""A fake satisfying the protocol proves services can be tested without a database."""

from __future__ import annotations

from collections.abc import Sequence

from genql.domain.entities.column import Column
from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.entities.datasource import Datasource
from genql.domain.entities.join_path import JoinPath
from genql.domain.ports.catalog_reader import CatalogReader
from genql.domain.ports.clustering_algorithm import ClusteringAlgorithm
from genql.domain.ports.datasource_repository import DatasourceRepository
from genql.domain.ports.join_path_miner import JoinPathMiner
from genql.domain.ports.join_path_writer import JoinPathWriter
from genql.domain.ports.node_embedder import NodeEmbedder
from genql.domain.ports.scope_resolver import ScopeResolver
from genql.domain.value_objects.query_scope import QueryScope
from genql.domain.value_objects.schema_ref import SchemaRef


class FakeCatalogReader:
    def read_objects(self, ref: SchemaRef) -> Sequence[DatabaseObject]:
        return []

    def read_columns(self, ref: SchemaRef) -> Sequence[Column]:
        return []

    def read_constraints(self, ref: SchemaRef) -> Sequence[Constraint]:
        return []


def test_a_plain_class_satisfies_the_port() -> None:
    assert isinstance(FakeCatalogReader(), CatalogReader)


class FakeDatasourceRepository:
    def add(self, datasource: Datasource) -> None: ...

    def get(self, name: str) -> Datasource:
        return Datasource(name=name, dialect="postgres", dsn_env_var="X")

    def update(self, datasource: Datasource) -> None: ...

    def list_all(self, enabled_only: bool = False) -> Sequence[Datasource]:
        return []

    def remove(self, name: str) -> None: ...


class FakeScopeResolver:
    def resolve(self, datasource_name: str | None, schema_names: Sequence[str]) -> QueryScope:
        return QueryScope(datasource_name="local", schema_names=("tpcds",))


def test_a_plain_class_satisfies_the_datasource_repository_port() -> None:
    assert isinstance(FakeDatasourceRepository(), DatasourceRepository)


def test_a_plain_class_satisfies_the_scope_resolver_port() -> None:
    assert isinstance(FakeScopeResolver(), ScopeResolver)


class FakeClusteringAlgorithm:
    def detect(self, datasource_name: str) -> int:
        return 0


class FakeNodeEmbedder:
    def embed(self, datasource_name: str) -> int:
        return 0


class FakeJoinPathMiner:
    def mine(self, datasource_name: str) -> Sequence[JoinPath]:
        return []


class FakeJoinPathWriter:
    def write(self, paths: Sequence[JoinPath]) -> int:
        return len(paths)


def test_a_plain_class_satisfies_the_clustering_algorithm_port() -> None:
    assert isinstance(FakeClusteringAlgorithm(), ClusteringAlgorithm)


def test_a_plain_class_satisfies_the_node_embedder_port() -> None:
    assert isinstance(FakeNodeEmbedder(), NodeEmbedder)


def test_a_plain_class_satisfies_the_join_path_miner_port() -> None:
    assert isinstance(FakeJoinPathMiner(), JoinPathMiner)


def test_a_plain_class_satisfies_the_join_path_writer_port() -> None:
    assert isinstance(FakeJoinPathWriter(), JoinPathWriter)
