"""FastRP writes an embedding onto every node it can reach."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from neo4j import Driver

from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.object_type import ObjectType
from genql.infrastructure.graph.gds_client_provider import GdsClientProvider
from genql.infrastructure.graph.neo4j_driver import create_neo4j_driver
from genql.repositories.graph.graph_writer_repository import Neo4jGraphWriterRepository
from genql.repositories.graph.node_embedder_repository import FastRpNodeEmbedder


@pytest.fixture()
def projected_graph(neo4j_uri: str) -> Iterator[Driver]:
    drv = create_neo4j_driver(neo4j_uri, "neo4j", "genqlgenql")
    with drv.session() as session:
        session.run("MATCH (o:Object {datasource_name: 'fastrp_test'}) DETACH DELETE o")
    Neo4jGraphWriterRepository(drv).write_objects(
        [
            DatabaseObject(
                datasource_name="fastrp_test",
                schema_name="s",
                object_name="only",
                object_type=ObjectType.TABLE,
            )
        ]
    )
    yield drv
    drv.close()


def test_fastrp_writes_an_embedding_onto_every_node(projected_graph: Driver) -> None:
    provider = GdsClientProvider(projected_graph)

    embedded = FastRpNodeEmbedder(provider).embed("fastrp_test")

    assert embedded == 1
    with projected_graph.session() as session:
        embedding = session.run(
            "MATCH (o:Object {datasource_name: 'fastrp_test'}) RETURN o.embedding AS e"
        ).single()["e"]
    assert embedding is not None
    assert len(embedding) == 128
