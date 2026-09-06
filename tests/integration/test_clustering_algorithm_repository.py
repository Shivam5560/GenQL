"""Leiden writes a community_id onto every node it can reach."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from neo4j import Driver

from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.constraint_type import ConstraintType
from genql.domain.value_objects.object_type import ObjectType
from genql.infrastructure.graph.gds_client_provider import GdsClientProvider
from genql.infrastructure.graph.neo4j_driver import create_neo4j_driver
from genql.repositories.graph.clustering_algorithm_repository import LeidenClusteringAlgorithm
from genql.repositories.graph.graph_writer_repository import Neo4jGraphWriterRepository


@pytest.fixture()
def projected_graph(neo4j_uri: str) -> Iterator[Driver]:
    drv = create_neo4j_driver(neo4j_uri, "neo4j", "genqlgenql")
    with drv.session() as session:
        session.run("MATCH (o:Object {datasource_name: 'leiden_test'}) DETACH DELETE o")
    writer = Neo4jGraphWriterRepository(drv)
    writer.write_objects(
        [
            DatabaseObject(
                datasource_name="leiden_test",
                schema_name="s",
                object_name=name,
                object_type=ObjectType.TABLE,
            )
            for name in ("a", "b")
        ]
    )
    writer.write_edges(
        [
            Constraint(
                datasource_name="leiden_test",
                schema_name="s",
                object_name="a",
                constraint_name="a_b_fkey",
                constraint_type=ConstraintType.FOREIGN_KEY,
                definition="FOREIGN KEY (b_id) REFERENCES b(id)",
                referenced_object_name="b",
            )
        ]
    )
    yield drv
    drv.close()


def test_leiden_writes_a_community_id_onto_every_node(projected_graph: Driver) -> None:
    provider = GdsClientProvider(projected_graph)

    communities_found = LeidenClusteringAlgorithm(provider).detect("leiden_test")

    assert communities_found >= 1
    with projected_graph.session() as session:
        missing = session.run(
            "MATCH (o:Object {datasource_name: 'leiden_test'}) "
            "WHERE o.community_id IS NULL RETURN count(o) AS n"
        ).single()["n"]
    assert missing == 0
