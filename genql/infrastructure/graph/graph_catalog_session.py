"""A GDS in-memory graph, scoped to one datasource, always dropped on exit.

Nodes are not separated by Neo4j database — Community Edition has one — so
every analysis run projects a named, Cypher-filtered graph containing only
that datasource's `:Object` nodes and `:REFERENCES` edges, and drops it
unconditionally when the `with` block ends. A crashed run can therefore never
leave a stale entry behind to collide with the next one, and two datasources
can never collide with each other either, since the graph name is derived
from the datasource name.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any, Literal

from genql.infrastructure.graph.gds_client_provider import GdsClientProvider

_NODE_QUERY = "MATCH (o:Object {datasource_name: $datasource_name}) RETURN id(o) AS id"
_RELATIONSHIP_QUERY = (
    "MATCH (s:Object {datasource_name: $datasource_name})"
    "-[:REFERENCES]->(t:Object {datasource_name: $datasource_name}) "
    "RETURN id(s) AS source, id(t) AS target"
)

# The legacy `gds.graph.project.cypher` procedure always marks its projected
# relationship set as directed (`direction: "DIRECTED"` in the graph's own
# schema, confirmed by inspecting a live projection) regardless of how the
# Cypher pattern was written — an undirected MATCH pattern, or a query that
# returns each edge in both directions, changes nothing, since GDS algorithms
# check this orientation flag, not whether the edge set happens to be
# symmetric. The only way to get a genuinely undirected relationship set is
# `gds.graph.relationships.toUndirected`, which derives a second, explicitly
# undirected relationship type from the projected one. Every caller that
# needs undirected traversal — Leiden (undefined on directed graphs) and
# join-path mining (must reach dim2 from dim1 through a shared fact table,
# even though the FK edges themselves only point fact -> dim) — must pass
# this name as its `relationshipTypes`/`relationship_types` argument; a
# caller that has no reason to ignore edge direction (FastRP's structural
# embeddings, where the fact-points-to-dimension direction is itself real
# signal) uses the graph's default relationship set instead.
UNDIRECTED_RELATIONSHIP_TYPE = "REFERENCES_UNDIRECTED"


class GraphCatalogSession:
    def __init__(self, gds_provider: GdsClientProvider, datasource_name: str) -> None:
        self._gds_provider = gds_provider
        self._datasource_name = datasource_name
        self._graph: Any = None

    def __enter__(self) -> Any:
        gds: Any = self._gds_provider.client()
        self._graph, _ = gds.graph.project.cypher(
            f"graph_{self._datasource_name}",
            _NODE_QUERY,
            _RELATIONSHIP_QUERY,
            parameters={"datasource_name": self._datasource_name},
        )
        gds.graph.relationships.toUndirected(
            self._graph,
            relationship_type="__ALL__",
            mutate_relationship_type=UNDIRECTED_RELATIONSHIP_TYPE,
        )
        return self._graph

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> Literal[False]:
        if self._graph is not None:
            self._graph.drop()
        return False
