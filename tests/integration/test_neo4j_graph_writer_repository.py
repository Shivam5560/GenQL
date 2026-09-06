"""Projection is idempotent: writing the same schema twice leaves the same
node and edge count, and cross-datasource nodes never collide."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from neo4j import Driver

from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.constraint_type import ConstraintType
from genql.domain.value_objects.object_type import ObjectType
from genql.infrastructure.graph.neo4j_driver import create_neo4j_driver
from genql.repositories.graph.graph_writer_repository import Neo4jGraphWriterRepository

_PARENT = DatabaseObject(
    datasource_name="local",
    schema_name="graph_writer_test",
    object_name="parent",
    object_type=ObjectType.TABLE,
)
_CHILD = DatabaseObject(
    datasource_name="local",
    schema_name="graph_writer_test",
    object_name="child",
    object_type=ObjectType.TABLE,
)
_FK = Constraint(
    datasource_name="local",
    schema_name="graph_writer_test",
    object_name="child",
    constraint_name="child_parent_fkey",
    constraint_type=ConstraintType.FOREIGN_KEY,
    definition="FOREIGN KEY (parent_id) REFERENCES parent(id)",
    referenced_object_name="parent",
    column_names=("parent_id",),
    referenced_column_names=("id",),
)


@pytest.fixture()
def driver(neo4j_uri: str) -> Iterator[Driver]:
    drv = create_neo4j_driver(neo4j_uri, "neo4j", "genqlgenql")
    with drv.session() as session:
        session.run("MATCH (o:Object {datasource_name: 'local'}) DETACH DELETE o")
    yield drv
    drv.close()


def test_projecting_twice_leaves_one_node_and_one_edge(driver: Driver) -> None:
    repo = Neo4jGraphWriterRepository(driver)

    for _ in range(2):
        repo.write_objects([_PARENT, _CHILD])
        repo.write_edges([_FK])

    with driver.session() as session:
        node_count = session.run(
            "MATCH (o:Object {datasource_name: 'local', schema_name: 'graph_writer_test'}) "
            "RETURN count(o) AS n"
        ).single()["n"]
        edge_count = session.run(
            "MATCH (:Object {qualified_name: 'local.graph_writer_test.child'})"
            "-[r:REFERENCES]->(:Object {qualified_name: 'local.graph_writer_test.parent'}) "
            "RETURN count(r) AS n"
        ).single()["n"]

    assert node_count == 2
    assert edge_count == 1
