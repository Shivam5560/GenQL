"""Mines the FK-graph shortest path between object pairs with no direct FK
edge.

Weights are uniform for now — there is no query log yet to weight edges by
join frequency. `Settings.join_path_strategy` is the seam Phase 6 uses to
register a query-weighted successor without touching any call site.
"""

from __future__ import annotations

from collections.abc import Sequence

from neo4j import Driver

from genql.domain.entities.join_path import JoinPath
from genql.infrastructure.graph.gds_client_provider import GdsClientProvider
from genql.infrastructure.graph.graph_catalog_session import GraphCatalogSession
from genql.repositories.graph.registry import JOIN_PATH_STRATEGIES

_LIST_OBJECTS_AND_EDGES = """
MATCH (o:Object {datasource_name: $datasource_name})
OPTIONAL MATCH (o)-[:REFERENCES]->(t:Object {datasource_name: $datasource_name})
RETURN o.object_name AS object_name, o.schema_name AS schema_name,
       collect(t.object_name) AS targets
"""

_SHORTEST_PATH = """
MATCH (source:Object {datasource_name: $datasource_name, object_name: $source_object})
MATCH (target:Object {datasource_name: $datasource_name, object_name: $target_object})
CALL gds.shortestPath.dijkstra.stream($graph_name, {sourceNode: source, targetNode: target})
YIELD path
RETURN [n IN nodes(path) | n.object_name] AS names, length(path) AS hops
"""


def _candidate_pairs(
    objects: Sequence[str], direct_edges: Sequence[tuple[str, str]]
) -> list[tuple[str, str]]:
    connected = {frozenset(edge) for edge in direct_edges}
    pairs: list[tuple[str, str]] = []
    for i, source in enumerate(objects):
        for target in objects[i + 1 :]:
            if frozenset((source, target)) not in connected:
                pairs.append((source, target))
    return pairs


@JOIN_PATH_STRATEGIES.register("weighted_shortest_path")
class WeightedShortestPathJoinPathMiner:
    """Takes the Neo4j driver directly for the plain Cypher reads (listing
    objects and edges, running the per-pair shortest path), and the GDS
    client provider only for the algorithm-catalog projection — the
    graphdatascience client does not reliably expose its underlying driver
    across versions, so the driver is wired in independently rather than
    extracted from it."""

    def __init__(self, driver: Driver, gds_provider: GdsClientProvider, max_hops: int = 4) -> None:
        self._driver = driver
        self._gds_provider = gds_provider
        self._max_hops = max_hops

    def mine(self, datasource_name: str) -> Sequence[JoinPath]:
        with self._driver.session() as session:
            rows = session.run(_LIST_OBJECTS_AND_EDGES, datasource_name=datasource_name).data()
        objects = [row["object_name"] for row in rows]
        schema_names = {row["object_name"]: row["schema_name"] for row in rows}
        direct_edges = [
            (row["object_name"], target) for row in rows for target in row["targets"] if target
        ]

        paths: list[JoinPath] = []
        with GraphCatalogSession(self._gds_provider, datasource_name) as graph:
            for source, target in _candidate_pairs(objects, direct_edges):
                paths.extend(
                    self._mine_pair(
                        graph.name(), datasource_name, schema_names[source], source, target
                    )
                )
        return paths

    def _mine_pair(
        self,
        graph_name: str,
        datasource_name: str,
        schema_name: str,
        source: str,
        target: str,
    ) -> list[JoinPath]:
        with self._driver.session() as session:
            record = session.run(
                _SHORTEST_PATH,
                datasource_name=datasource_name,
                source_object=source,
                target_object=target,
                graph_name=graph_name,
            ).single()
        if record is None or record["hops"] > self._max_hops:
            return []
        names = tuple(record["names"])
        return [
            JoinPath(
                datasource_name=datasource_name,
                schema_name=schema_name,
                source_object=source,
                target_object=target,
                path=names,
                weight=float(record["hops"]),
            )
        ]
