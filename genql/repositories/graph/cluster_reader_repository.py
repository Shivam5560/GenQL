"""Reads back whichever clustering algorithm's node-property assignment —
Leiden's community_id or fused clustering's domain_cluster — grouped by
cluster id. Not registry-based: it has one implementation and is wired
directly, the same treatment Neo4jGraphWriterRepository already gets."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence

from neo4j import Driver
from neo4j.exceptions import DriverError, Neo4jError

from genql.domain.errors import DomainNamingError

_READ_CLUSTERS = (
    "MATCH (o:Object {datasource_name: $datasource_name}) "
    "WHERE properties(o)[$property_name] IS NOT NULL "
    "RETURN o.qualified_name AS qualified_name, properties(o)[$property_name] AS cluster_id"
)


class Neo4jClusterReader:
    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def read_clusters(
        self, datasource_name: str, property_name: str
    ) -> Mapping[int, Sequence[str]]:
        try:
            with self._driver.session() as session:
                rows = list(
                    session.run(
                        _READ_CLUSTERS,
                        datasource_name=datasource_name,
                        property_name=property_name,
                    )
                )
        except (Neo4jError, DriverError) as exc:
            raise DomainNamingError(
                f"failed to read {property_name!r} clusters for {datasource_name!r}: {exc}"
            ) from exc
        clusters: dict[int, list[str]] = defaultdict(list)
        for row in rows:
            clusters[int(row["cluster_id"])].append(row["qualified_name"])
        return clusters
