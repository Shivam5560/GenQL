"""Orchestrates fused clustering, reading the assignment back out of Neo4j,
naming each cluster, and persisting domains and their members. `clustering`
is resolved to the `fused` ClusteringAlgorithm at the composition root — this
service does not know or care which algorithm it is, same rule
GraphAnalysisService already follows for `leiden`."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.domain_member import DomainMember
from genql.domain.ports.cluster_reader import ClusterReader
from genql.domain.ports.clustering_algorithm import ClusteringAlgorithm
from genql.domain.ports.domain_namer import DomainNamer
from genql.domain.ports.domain_writer import DomainWriter
from genql.domain.ports.enrichment_reader import EnrichmentReader

_FUSED_PROPERTY = "domain_cluster"


class DomainDiscoveryReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    domains: int
    members: int


class DomainDiscoveryService:
    def __init__(
        self,
        clustering: ClusteringAlgorithm,
        cluster_reader: ClusterReader,
        enrichment_reader: EnrichmentReader,
        namer: DomainNamer,
        domain_writer: DomainWriter,
    ) -> None:
        self._clustering = clustering
        self._cluster_reader = cluster_reader
        self._enrichment_reader = enrichment_reader
        self._namer = namer
        self._domain_writer = domain_writer

    def discover(self, datasource_name: str) -> DomainDiscoveryReport:
        self._clustering.detect(datasource_name)
        clusters_by_id = self._cluster_reader.read_clusters(datasource_name, _FUSED_PROPERTY)
        enrichment_by_qn = {
            e.qualified_name: e
            for e in self._enrichment_reader.read_object_enrichments(datasource_name)
        }

        cluster_ids = sorted(clusters_by_id)
        ordered_clusters = {
            cid: [enrichment_by_qn[qn] for qn in clusters_by_id[cid] if qn in enrichment_by_qn]
            for cid in cluster_ids
        }
        named = self._namer.name(datasource_name, ordered_clusters)

        written = self._domain_writer.write_domains(named)
        members = [
            DomainMember(
                domain_id=domain.domain_id,  # populated by write_domains
                datasource_name=datasource_name,
                schema_name=qn.split(".")[1],
                object_name=qn.split(".")[2],
            )
            for cluster_id, domain in zip(cluster_ids, written, strict=True)
            for qn in clusters_by_id[cluster_id]
        ]
        written_members = self._domain_writer.write_members(members)
        return DomainDiscoveryReport(domains=len(written), members=written_members)
