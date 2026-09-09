"""Produces one candidate on the non-contested path, or several representing
alternative interpretations on the contested path.

Non-contested: exactly one strategy (the factory's `default`, since a
non-contested plan has one intended reading and strategy choice cannot
matter), keeping only its first variant, with examples=() — bit-for-bit Phase
5/6 behaviour and cost. Contested: fetches up to `ambiguity_example_top_k`
examples once, then calls every strategy the factory offers with them,
flattening the variants into one tuple. Two strategies therefore yield four
candidates through exactly two ChatProvider calls, matching the parent spec's
§20 cost model.

Which strategies exist is `CandidateStrategyFactory`'s business, not this
service's: the registry that answers that question lives under
`genql.repositories`, which the services layer never imports.

`escalated` picks which ChatProvider the strategies are built with —
chat_model normally, chat_model_escalation for the one regeneration this
phase allows after every survivor was judged fatal.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import GenerationError
from genql.domain.ports.ambiguity_example_reader import AmbiguityExampleReader
from genql.domain.ports.candidate_strategy_factory import CandidateStrategyFactory
from genql.domain.ports.chat_provider import ChatProvider


class CandidateGenerationService:
    def __init__(  # noqa: PLR0913, PLR0917 - one dependency per collaborator
        self,
        chat: ChatProvider,
        escalation_chat: ChatProvider,
        strategies: CandidateStrategyFactory,
        examples: AmbiguityExampleReader,
        example_top_k: int,
    ) -> None:
        self._chat = chat
        self._escalation_chat = escalation_chat
        self._strategies = strategies
        self._examples = examples
        self._example_top_k = example_top_k

    def generate(  # noqa: PLR0913, PLR0917 - one flag per generation mode the brief's interface requires
        self,
        plan: QueryPlan,
        links: tuple[SchemaLink, ...],
        violations: tuple[GuardrailViolation, ...] = (),
        *,
        domain_id: int | None = None,
        contested: bool = False,
        escalated: bool = False,
    ) -> tuple[SqlCandidate, ...]:
        if not links:
            raise GenerationError(f"cannot generate SQL for {plan.question!r} with no schema links")
        chat = self._escalation_chat if escalated else self._chat

        if not contested:
            strategy = self._strategies.default(chat)
            return strategy.generate_variants(plan, links, violations, ())[:1]

        examples = self._examples.search(plan.question, domain_id, self._example_top_k)
        strategies = self._strategies.all(chat)
        # Each strategy is one independent ChatProvider.complete call with no
        # shared state — the dominant cost of the contested path is exactly
        # these calls run one after another, so running them concurrently
        # (blocking I/O, hence threads rather than asyncio — this whole
        # pipeline is synchronous by design, see genql/api/app.py) turns N
        # sequential round trips into the slowest single one.
        with ThreadPoolExecutor(max_workers=len(strategies)) as pool:
            futures = [
                pool.submit(strategy.generate_variants, plan, links, violations, examples)
                for strategy in strategies
            ]
            results = [future.result() for future in futures]
        return tuple(candidate for variants in results for candidate in variants)
