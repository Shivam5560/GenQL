"""LlmDomainNamer consumes the ChatProvider port, so it is unit-testable
with a fake — unlike OpenRouterChatProvider itself, which IS that port's
implementation and is integration-tested against the real API instead."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeVar

from pydantic import BaseModel

from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.repositories.semantic.domain_namer_repository import LlmDomainNamer

T = TypeVar("T", bound=BaseModel)

MEMBER = ObjectEnrichment(
    datasource_name="local",
    schema_name="shop",
    object_name="orders",
    description="Customer orders.",
)


class FakeChatProvider:
    def complete(self, prompt: str, response_schema: type[T]) -> T:
        return response_schema.model_validate({"name": "sales", "description": "Sales activity."})


def test_name_returns_one_domain_per_cluster_in_order() -> None:
    namer = LlmDomainNamer(FakeChatProvider())
    clusters: Mapping[int, Sequence[ObjectEnrichment]] = {0: [MEMBER], 1: [MEMBER]}

    domains = namer.name("local", clusters)

    assert len(domains) == 2
    assert domains[0].name == "sales"
    assert domains[0].datasource_name == "local"
