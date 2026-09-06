"""A fake satisfying each protocol proves the corresponding service can be
tested without a database, an LLM, or a network call."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel

from genql.domain.entities.business_domain import BusinessDomain
from genql.domain.entities.column_enrichment import ColumnEnrichment
from genql.domain.entities.domain_member import DomainMember
from genql.domain.entities.enrichment_field import EnrichmentField
from genql.domain.entities.metric import Metric
from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.domain.ports.chat_provider import ChatProvider
from genql.domain.ports.cluster_reader import ClusterReader
from genql.domain.ports.comment_writer import CommentWriter
from genql.domain.ports.domain_namer import DomainNamer
from genql.domain.ports.domain_writer import DomainWriter
from genql.domain.ports.embedding_provider import EmbeddingProvider
from genql.domain.ports.enricher import Enricher
from genql.domain.ports.enrichment_reader import EnrichmentReader
from genql.domain.ports.enrichment_writer import EnrichmentWriter
from genql.domain.ports.metric_writer import MetricWriter
from genql.domain.ports.rerank_provider import RerankProvider, RerankScore
from genql.domain.ports.retriever import Retriever, SearchResult
from genql.domain.ports.search_document_writer import SearchDocumentWriter
from genql.domain.value_objects.schema_ref import SchemaRef


class FakeChatProvider:
    def complete(self, prompt: str, response_schema: type[BaseModel]) -> BaseModel:
        return response_schema.model_validate({})


class FakeEmbeddingProvider:
    def embed(self, texts: Sequence[str]) -> Sequence[tuple[float, ...]]:
        return [(0.0,) for _ in texts]


class FakeRerankProvider:
    def rerank(self, query: str, documents: Sequence[str], top_n: int) -> Sequence[RerankScore]:
        return [RerankScore(index=i, score=1.0) for i in range(min(top_n, len(documents)))]


class FakeEnrichmentReader:
    def read_object_enrichments(self, datasource_name: str) -> Sequence[ObjectEnrichment]:
        return []

    def read_column_enrichments(self, ref: SchemaRef) -> Sequence[ColumnEnrichment]:
        return []


class FakeEnrichmentWriter:
    def write_object_enrichment(self, enrichment: ObjectEnrichment) -> None:
        return None

    def write_column_enrichments(self, enrichments: Sequence[ColumnEnrichment]) -> int:
        return len(enrichments)


class FakeDomainWriter:
    def write_domains(self, domains: Sequence[BusinessDomain]) -> Sequence[BusinessDomain]:
        return domains

    def write_members(self, members: Sequence[DomainMember]) -> int:
        return len(members)


class FakeDomainNamer:
    def name(
        self, datasource_name: str, clusters: Mapping[int, Sequence[ObjectEnrichment]]
    ) -> Sequence[BusinessDomain]:
        return []


class FakeMetricWriter:
    def write(self, metrics: Sequence[Metric]) -> int:
        return len(metrics)


class FakeEnricher:
    key = "description"

    def merge(
        self, discovered: EnrichmentField | None, overlay: EnrichmentField | None
    ) -> EnrichmentField | None:
        return overlay or discovered


class FakeSearchDocumentWriter:
    def compile(self, datasource_name: str) -> int:
        return 0


class FakeCommentWriter:
    def write_object_comment(self, ref: SchemaRef, object_name: str, comment: str) -> None:
        return None

    def write_column_comment(
        self, ref: SchemaRef, object_name: str, column_name: str, comment: str
    ) -> None:
        return None


class FakeRetriever:
    def search(
        self,
        datasource_name: str,
        query: str,
        query_embedding: Sequence[float],
        top_k: int,
        domain_id: int | None = None,
    ) -> Sequence[SearchResult]:
        return []


class FakeClusterReader:
    def read_clusters(
        self, datasource_name: str, property_name: str
    ) -> Mapping[int, Sequence[str]]:
        return {}


def test_a_plain_class_satisfies_each_new_port() -> None:
    assert isinstance(FakeChatProvider(), ChatProvider)
    assert isinstance(FakeEmbeddingProvider(), EmbeddingProvider)
    assert isinstance(FakeRerankProvider(), RerankProvider)
    assert isinstance(FakeEnrichmentReader(), EnrichmentReader)
    assert isinstance(FakeEnrichmentWriter(), EnrichmentWriter)
    assert isinstance(FakeDomainWriter(), DomainWriter)
    assert isinstance(FakeDomainNamer(), DomainNamer)
    assert isinstance(FakeMetricWriter(), MetricWriter)
    assert isinstance(FakeEnricher(), Enricher)
    assert isinstance(FakeSearchDocumentWriter(), SearchDocumentWriter)
    assert isinstance(FakeCommentWriter(), CommentWriter)
    assert isinstance(FakeRetriever(), Retriever)
    assert isinstance(FakeClusterReader(), ClusterReader)
