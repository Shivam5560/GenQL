"""One LLM call per cluster, naming it from its member objects' descriptions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel

from genql.domain.entities.business_domain import BusinessDomain
from genql.domain.entities.object_enrichment import ObjectEnrichment
from genql.domain.errors import ChatProviderError, DomainNamingError
from genql.domain.ports.chat_provider import ChatProvider


class _DomainNameResponse(BaseModel):
    name: str
    description: str


class LlmDomainNamer:
    def __init__(self, chat: ChatProvider) -> None:
        self._chat = chat

    def name(
        self, datasource_name: str, clusters: Mapping[int, Sequence[ObjectEnrichment]]
    ) -> Sequence[BusinessDomain]:
        domains: list[BusinessDomain] = []
        for cluster_id, members in clusters.items():
            member_lines = "\n".join(f"- {m.object_name}: {m.description}" for m in members)
            prompt = (
                "These database objects were clustered together by structural and semantic "
                "similarity:\n" + member_lines + "\n"
                "Give this cluster a two-to-three word business domain name and a one-sentence "
                "description grounded in what the member objects above actually are."
            )
            try:
                response = self._chat.complete(prompt, _DomainNameResponse)
            except ChatProviderError as exc:
                raise DomainNamingError(
                    f"failed to name cluster {cluster_id} for {datasource_name!r}: {exc}"
                ) from exc
            domains.append(
                BusinessDomain(
                    datasource_name=datasource_name,
                    name=response.name,
                    description=response.description,
                )
            )
        return domains
