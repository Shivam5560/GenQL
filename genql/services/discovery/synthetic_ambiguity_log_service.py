"""Offline: for each domain, one ChatProvider call grounded on that domain's
name, description, and the datasource's full metric list (Deviation 5) asks
for several genuinely ambiguous example questions with their interpretations
and resolution, embeds each question, and writes them via
AmbiguityExampleWriter.

Zero domains is valid, not an error (Deviation 6): the first `genql discover`
run reaches this step before `genql graph domains` has ever populated
genql_domain. Re-running `genql discover --start-from synthetic_ambiguity_log`
after domain naming is the intended path to populate the log for real.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, ValidationError

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.domain.entities.business_domain import BusinessDomain
from genql.domain.entities.metric import Metric
from genql.domain.errors import (
    AmbiguityExampleGenerationError,
    ChatProviderError,
    EmbeddingProviderError,
)
from genql.domain.ports.ambiguity_example_writer import AmbiguityExampleWriter
from genql.domain.ports.chat_provider import ChatProvider
from genql.domain.ports.domain_reader import DomainReader
from genql.domain.ports.embedding_provider import EmbeddingProvider
from genql.domain.ports.metric_reader import MetricReader


class ExampleResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: str
    interpretations: tuple[str, ...]
    resolution: str


class SyntheticAmbiguityLogResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    examples: tuple[ExampleResponse, ...] = ()


def build_prompt(domain: BusinessDomain, metrics: Sequence[Metric]) -> str:
    metric_names = ", ".join(m.name for m in metrics) or "(none defined)"
    return (
        "Write several genuinely ambiguous analytical questions a business "
        "user might ask about the domain below — questions that admit more "
        "than one reasonable interpretation — along with what those "
        "interpretations are and which one is actually correct, and why.\n\n"
        f"Domain: {domain.name}\n"
        f"Description: {domain.description}\n"
        f"Metrics available in this datasource: {metric_names}\n\n"
        "Rules:\n"
        "- Each example names at least two distinct interpretations.\n"
        "- `resolution` states which interpretation is correct and the "
        "business reasoning why, in prose.\n"
        "- Return `examples`; an empty list is valid if nothing genuinely "
        "ambiguous applies to this domain."
    )


class SyntheticAmbiguityLogService:
    def __init__(
        self,
        chat: ChatProvider,
        embedder: EmbeddingProvider,
        domains: DomainReader,
        metrics: MetricReader,
        writer: AmbiguityExampleWriter,
    ) -> None:
        self._chat = chat
        self._embedder = embedder
        self._domains = domains
        self._metrics = metrics
        self._writer = writer

    def generate(self, datasource_name: str) -> int:
        domains = self._domains.list_domains(datasource_name)
        if not domains:
            return 0
        metrics = self._metrics.read_metrics(datasource_name)

        written_total = 0
        for domain in domains:
            try:
                response = self._chat.complete(
                    build_prompt(domain, metrics), SyntheticAmbiguityLogResponse
                )
            except (ChatProviderError, ValidationError) as exc:
                raise AmbiguityExampleGenerationError(
                    f"failed to generate ambiguity examples for domain "
                    f"{domain.name!r} in {datasource_name!r}: {exc}"
                ) from exc
            if not response.examples:
                continue
            examples = tuple(
                AmbiguityExample(
                    question=e.question,
                    interpretations=e.interpretations,
                    resolution=e.resolution,
                    domain_id=domain.domain_id,
                )
                for e in response.examples
            )
            try:
                self._writer.write(examples)
            except EmbeddingProviderError as exc:
                raise AmbiguityExampleGenerationError(
                    f"failed to embed ambiguity examples for domain "
                    f"{domain.name!r} in {datasource_name!r}: {exc}"
                ) from exc
            written_total += len(examples)
        return written_total
