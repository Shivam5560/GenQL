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
# The legacy `gds.graph.project.cypher` procedure projects every (source,
# target) row the relationship query returns as a directed edge in that
# exact order — an undirected Cypher pattern (`-[:REFERENCES]-`, no
# arrowhead) still returns each relationship as ONE row, not one per
# direction, so it does NOT produce an undirected projection on its own
# (confirmed against a real Leiden run: "the Leiden algorithm works only
# with undirected graphs" fired even with the undirected pattern). The
# procedure has no orientation config, so the standard workaround is to
# return each edge twice, once per direction, via UNION ALL — Leiden (which
# is undefined on directed graphs) and join-path mining (which must reach
# dim2 from dim1 through a shared fact table, even though the FK edges
# themselves only point fact -> dim) then see a graph that behaves as
# undirected.
_RELATIONSHIP_QUERY = (
    "MATCH (s:Object {datasource_name: $datasource_name})"
    "-[:REFERENCES]->(t:Object {datasource_name: $datasource_name}) "
    "RETURN id(s) AS source, id(t) AS target "
    "UNION ALL "
    "MATCH (s:Object {datasource_name: $datasource_name})"
    "-[:REFERENCES]->(t:Object {datasource_name: $datasource_name}) "
    "RETURN id(t) AS source, id(s) AS target"
)


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
