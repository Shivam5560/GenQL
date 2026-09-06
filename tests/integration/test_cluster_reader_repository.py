from __future__ import annotations

from neo4j import Driver, GraphDatabase

from genql.repositories.graph.cluster_reader_repository import Neo4jClusterReader


def test_read_clusters_groups_qualified_names_by_cluster_id(neo4j_uri: str) -> None:
    driver: Driver = GraphDatabase.driver(neo4j_uri, auth=("neo4j", "genqlgenql"))
    ds = "cluster_reader_test"
    with driver.session() as session:
        session.run(
            "MERGE (a:Object {qualified_name: $qn, datasource_name: $ds, domain_cluster: 0})",
            qn=f"{ds}.shop.a",
            ds=ds,
        )
        session.run(
            "MERGE (b:Object {qualified_name: $qn, datasource_name: $ds, domain_cluster: 0})",
            qn=f"{ds}.shop.b",
            ds=ds,
        )

    clusters = Neo4jClusterReader(driver).read_clusters(ds, "domain_cluster")

    assert set(clusters[0]) == {f"{ds}.shop.a", f"{ds}.shop.b"}
    driver.close()
