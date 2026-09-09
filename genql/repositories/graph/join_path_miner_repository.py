"""Mines the FK-graph shortest path between object pairs with no direct FK
edge.

Weights are uniform for now — there is no query log yet to weight edges by
join frequency. `Settings.join_path_strategy` is the seam Phase 6 uses to
register a query-weighted successor without touching any call site.

Objects are looked up in the graph by `qualified_name`, not bare
`object_name`: two schemas of the same datasource can each hold an object
with the same name (Phase 2.5 supports n schemas per datasource), and a
bare-name match would collide across them. `JoinPath.source_object` /
`target_object` / `path` still carry plain object names — those are the
persisted entity's fields, not graph lookup keys.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, NamedTuple

from neo4j import Driver
from neo4j.exceptions import DriverError, Neo4jError

from genql.domain.entities.join_path import JoinPath
from genql.domain.errors import GraphAnalysisError
from genql.infrastructure.graph.gds_client_provider import GdsClientProvider
from genql.infrastructure.graph.graph_catalog_session import (
    UNDIRECTED_RELATIONSHIP_TYPE,
    GraphCatalogSession,
)
from genql.repositories.graph.registry import JOIN_PATH_STRATEGIES

_LIST_OBJECTS_AND_EDGES = """
MATCH (o:Object {datasource_name: $datasource_name})
OPTIONAL MATCH (o)-[:REFERENCES]->(t:Object {datasource_name: $datasource_name})
RETURN o.qualified_name AS qualified_name, o.object_name AS object_name,
       o.schema_name AS schema_name, collect(t.qualified_name) AS targets
"""

_SHORTEST_PATH = f"""
MATCH (source:Object {{datasource_name: $datasource_name, qualified_name: $source_qualified_name}})
MATCH (target:Object {{datasource_name: $datasource_name, qualified_name: $target_qualified_name}})
CALL gds.shortestPath.dijkstra.stream($graph_name, {{
    sourceNode: source, targetNode: target,
    relationshipTypes: ['{UNDIRECTED_RELATIONSHIP_TYPE}']
}})
YIELD path
RETURN [n IN nodes(path) | n.object_name] AS names, length(path) AS hops
"""


class _ObjectRef(NamedTuple):
    """An object identified both ways it is needed: by qualified_name for
    graph lookups, and by object_name for the persisted JoinPath fields."""

    qualified_name: str
    object_name: str


def _candidate_pairs(
    objects: Sequence[str], direct_edges: Sequence[tuple[str, str]]
) -> list[tuple[str, str]]:
    """Every unordered pair of objects with no direct FK edge between them.

    Cost characteristic: this is O(n^2) in the number of objects, and `mine`
    below issues one Cypher query per pair it returns — there is no
    candidate-pruning or batched query here. This is a known scaling limit
    for schemas with many objects and few FK edges.

    `gds.shortestPath.dijkstra` was checked against the installed
    `graphdatascience` client (`DijkstraCypherEndpoints` /
    `SourceTargetDijkstraEndpoints.stream`) for a native hop-limit
    parameter: its config surface is sourceNode, targetNodes,
    relationshipWeightProperty, relationshipTypes, nodeLabels, sudo,
    logProgress, username, concurrency, jobId — no depth/hop bound exists.
    `max_hops` is therefore necessarily applied as a post-filter in
    `_mine_pair`, after each query already ran.
    """
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
        rows = self._list_objects_and_edges(datasource_name)
        qualified_names = [row["qualified_name"] for row in rows]
        object_names = {row["qualified_name"]: row["object_name"] for row in rows}
        schema_names = {row["qualified_name"]: row["schema_name"] for row in rows}
        direct_edges = [
            (row["qualified_name"], target) for row in rows for target in row["targets"] if target
        ]

        paths: list[JoinPath] = []
        try:
            with GraphCatalogSession(self._gds_provider, datasource_name) as graph:
                for source_qn, target_qn in _candidate_pairs(qualified_names, direct_edges):
                    source = _ObjectRef(source_qn, object_names[source_qn])
                    target = _ObjectRef(target_qn, object_names[target_qn])
                    paths.extend(
                        self._mine_pair(
                            graph.name(), datasource_name, schema_names[source_qn], source, target
                        )
                    )
        except (Neo4jError, DriverError) as exc:
            raise GraphAnalysisError(
                f"failed to mine join paths for {datasource_name!r}: {exc}"
            ) from exc
        return paths

    def _list_objects_and_edges(self, datasource_name: str) -> list[dict[str, Any]]:
        try:
            with self._driver.session() as session:
                return session.run(_LIST_OBJECTS_AND_EDGES, datasource_name=datasource_name).data()
        except (Neo4jError, DriverError) as exc:
            raise GraphAnalysisError(
                f"failed to list objects and edges for {datasource_name!r}: {exc}"
            ) from exc

    def _mine_pair(
        self,
        graph_name: str,
        datasource_name: str,
        schema_name: str,
        source: _ObjectRef,
        target: _ObjectRef,
    ) -> list[JoinPath]:
        with self._driver.session() as session:
            record = session.run(
                _SHORTEST_PATH,
                datasource_name=datasource_name,
                source_qualified_name=source.qualified_name,
                target_qualified_name=target.qualified_name,
                graph_name=graph_name,
            ).single()
        if record is None or record["hops"] > self._max_hops:
            return []
        names = tuple(record["names"])
        return [
            JoinPath(
                datasource_name=datasource_name,
                schema_name=schema_name,
                source_object=source.object_name,
                target_object=target.object_name,
                path=names,
                weight=float(record["hops"]),
            )
        ]
