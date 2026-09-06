"""DomainDiscoveryService: fused-cluster, read the assignment back, name
each cluster, write domains and their members. All five dependencies are
ports."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from genql.domain.entities.business_domain import BusinessDomain
from genql.domain.entities.domain_member import DomainMember
from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.services.semantic.domain_discovery_service import DomainDiscoveryService

ENRICHMENT_A = ObjectEnrichment(
    datasource_name="local",
    schema_name="shop",
    object_name="a",
    description="x",
)
ENRICHMENT_B = ObjectEnrichment(
    datasource_name="local",
    schema_name="shop",
    object_name="b",
    description="y",
)


class FakeClustering:
    def detect(self, datasource_name: str) -> int:
        return 2


class FakeClusterReader:
    def read_clusters(
        self, datasource_name: str, property_name: str
    ) -> Mapping[int, Sequence[str]]:
        return {0: ["local.shop.a"], 1: ["local.shop.b"]}


class FakeEnrichmentReader:
    def read_object_enrichments(self, datasource_name: str) -> Sequence[ObjectEnrichment]:
        return [ENRICHMENT_A, ENRICHMENT_B]

    def read_column_enrichments(self, ref: object) -> Sequence[object]:
        return []


class FakeNamer:
    def name(
        self, datasource_name: str, clusters: Mapping[int, Sequence[ObjectEnrichment]]
    ) -> Sequence[BusinessDomain]:
        return [
            BusinessDomain(datasource_name=datasource_name, name=f"domain_{cid}", description="d")
            for cid in clusters
        ]


class FakeDomainWriter:
    def __init__(self) -> None:
        self.members: list[DomainMember] = []

    def write_domains(self, domains: Sequence[BusinessDomain]) -> Sequence[BusinessDomain]:
        return [
            BusinessDomain(**{**d.model_dump(), "domain_id": i}) for i, d in enumerate(domains, 1)
        ]

    def write_members(self, members: Sequence[DomainMember]) -> int:
        self.members.extend(members)
        return len(members)


def test_discover_names_each_cluster_and_writes_its_members() -> None:
    writer = FakeDomainWriter()
    service = DomainDiscoveryService(
        FakeClustering(), FakeClusterReader(), FakeEnrichmentReader(), FakeNamer(), writer
    )

    report = service.discover("local")

    assert report.domains == 2
    assert report.members == 2
    member_by_object = {m.object_name: m.domain_id for m in writer.members}
    assert member_by_object["a"] == 1
    assert member_by_object["b"] == 2
