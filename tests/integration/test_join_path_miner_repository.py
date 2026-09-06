"""Mines the FK route between two objects that are connected only through a
third — the case a direct-edge-only view of the FK graph cannot answer."""

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
from genql.repositories.graph.graph_writer_repository import Neo4jGraphWriterRepository
from genql.repositories.graph.join_path_miner_repository import WeightedShortestPathJoinPathMiner


@pytest.fixture()
def chain_graph(neo4j_uri: str) -> Iterator[Driver]:
    """a -> b -> c: a and c are two hops apart, never directly FK-connected."""
    drv = create_neo4j_driver(neo4j_uri, "neo4j", "genqlgenql")
    with drv.session() as session:
        session.run("MATCH (o:Object {datasource_name: 'join_path_test'}) DETACH DELETE o")
    writer = Neo4jGraphWriterRepository(drv)
    writer.write_objects(
        [
            DatabaseObject(
                datasource_name="join_path_test",
                schema_name="s",
                object_name=name,
                object_type=ObjectType.TABLE,
            )
            for name in ("a", "b", "c")
        ]
    )
    writer.write_edges(
        [
            Constraint(
                datasource_name="join_path_test",
                schema_name="s",
                object_name="a",
                constraint_name="a_b_fkey",
                constraint_type=ConstraintType.FOREIGN_KEY,
                definition="FOREIGN KEY (b_id) REFERENCES b(id)",
                referenced_object_name="b",
            ),
            Constraint(
                datasource_name="join_path_test",
                schema_name="s",
                object_name="b",
                constraint_name="b_c_fkey",
                constraint_type=ConstraintType.FOREIGN_KEY,
                definition="FOREIGN KEY (c_id) REFERENCES c(id)",
                referenced_object_name="c",
            ),
        ]
    )
    yield drv
    drv.close()


def test_mines_the_two_hop_path_between_a_and_c(chain_graph: Driver) -> None:
    provider = GdsClientProvider(chain_graph)
    miner = WeightedShortestPathJoinPathMiner(chain_graph, provider, max_hops=4)

    paths = miner.mine("join_path_test")

    a_to_c = [p for p in paths if {p.source_object, p.target_object} == {"a", "c"}]
    assert len(a_to_c) == 1
    assert set(a_to_c[0].path) == {"a", "b", "c"}
    assert a_to_c[0].schema_name == "s"


def test_directly_connected_pairs_are_not_mined(chain_graph: Driver) -> None:
    provider = GdsClientProvider(chain_graph)
    miner = WeightedShortestPathJoinPathMiner(chain_graph, provider, max_hops=4)

    paths = miner.mine("join_path_test")

    a_to_b = [p for p in paths if {p.source_object, p.target_object} == {"a", "b"}]
    assert a_to_b == []
