"""Stage 3 of the parent spec's §9, and the first real caller of Phase 4's
domain-scoped retrieval path.

The heuristic is deliberately plain: one unscoped retrieval pass, a plurality
vote over the domain_name each hit carries, one name-to-id lookup. There is no
confidence floor, and a wrongly-resolved domain narrows retrieval to the wrong
slice of the schema — which is exactly the risk the spec's §11 names and
accepts. It is accepted because --domain-id remains a manual override for that
failure mode, and because real disambiguation (asking the user, or making
domain a seventh ambiguity dimension) is a design decision worth making on
evidence rather than half-building here.

None is returned, not raised, wherever the vote has nothing to work with: an
empty sample, a sample with no domains at all, or a domain name the store no
longer knows. All three mean "search unscoped", which is precisely what Phase 5
did on every question. A retrieval failure IS raised, because that means the
turn cannot search at all.
"""

from __future__ import annotations

from collections import Counter

from genql.domain.errors import DomainScopingError, RetrievalError
from genql.domain.ports.domain_reader import DomainReader
from genql.services.semantic.retrieval_service import RetrievalService


class DomainScopingService:
    def __init__(
        self, retrieval: RetrievalService, domains: DomainReader, sample_size: int
    ) -> None:
        self._retrieval = retrieval
        self._domains = domains
        self._sample_size = sample_size

    def resolve(self, question: str, datasource_name: str) -> int | None:
        try:
            # rerank=False: the vote below reads the *set* of domains the hits
            # carry, and Counter is insensitive to their order except when
            # breaking a tie. Reranking would spend a full provider round trip
            # per turn to influence only that tie-break, so it is skipped here.
            # SchemaLinkingService — the caller that genuinely ranks — still
            # reranks.
            results = self._retrieval.search(
                datasource_name, question, self._sample_size, rerank=False
            )
        except RetrievalError as exc:
            raise DomainScopingError(
                f"failed to sample {datasource_name!r} for {question!r}: {exc}"
            ) from exc

        names = [r.domain_name for r in results if r.domain_name]
        if not names:
            return None
        # Counter.most_common breaks ties by first insertion, and `results` is
        # already ranked by the retriever itself, so a tie resolves to the
        # better-ranked hit's domain even though this pass skips reranking.
        plurality, _ = Counter(names).most_common(1)[0]
        return self._domains.domain_id_by_name(datasource_name, plurality)
