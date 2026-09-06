"""Seeds two well-separated fake FastRP embeddings directly onto Neo4j nodes
and two matching text embeddings through a fake EnrichmentReader, then
asserts fused clustering finds two clusters and writes domain_cluster."""

from __future__ import annotations

from collections.abc import Sequence

from neo4j import Driver, GraphDatabase

from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.repositories.graph.fused_clustering_algorithm_repository import (
    FusedClusteringAlgorithm,
)


class FakeEnrichmentReader:
    def __init__(self, enrichments: Sequence[ObjectEnrichment]) -> None:
        self._enrichments = enrichments

    def read_object_enrichments(self, datasource_name: str) -> Sequence[ObjectEnrichment]:
        return self._enrichments

    def read_column_enrichments(self, ref: object) -> Sequence[object]:
        return []


def test_detect_finds_two_clusters_and_writes_domain_cluster(neo4j_uri: str) -> None:
    driver: Driver = GraphDatabase.driver(neo4j_uri, auth=("neo4j", "genqlgenql"))
    ds = "fused_test"
    with driver.session() as session:
        session.run(
            "MERGE (a:Object {qualified_name: $qn, datasource_name: $ds}) SET a.embedding = $e",
            qn=f"{ds}.shop.a",
            ds=ds,
            e=[0.0] * 8,
        )
        session.run(
            "MERGE (b:Object {qualified_name: $qn, datasource_name: $ds}) SET b.embedding = $e",
            qn=f"{ds}.shop.b",
            ds=ds,
            e=[10.0] * 8,
        )
    enrichments = [
        ObjectEnrichment(
            datasource_name=ds,
            schema_name="shop",
            object_name="a",
            description="x",
            embedding=tuple([0.0] * 8),
        ),
        ObjectEnrichment(
            datasource_name=ds,
            schema_name="shop",
            object_name="b",
            description="y",
            embedding=tuple([10.0] * 8),
        ),
    ]
    algorithm = FusedClusteringAlgorithm(
        driver, FakeEnrichmentReader(enrichments), k_min=2, k_max=2
    )

    k = algorithm.detect(ds)

    assert k == 2
    with driver.session() as session:
        clusters = {
            r["qn"]: r["c"]
            for r in session.run(
                "MATCH (o:Object {datasource_name: $ds}) RETURN o.qualified_name AS qn, "
                "o.domain_cluster AS c",
                ds=ds,
            )
        }
    assert clusters[f"{ds}.shop.a"] != clusters[f"{ds}.shop.b"]
    driver.close()
