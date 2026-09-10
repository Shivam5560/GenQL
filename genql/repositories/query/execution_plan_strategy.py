"""Asks the model to reason in terms of a PostgreSQL execution plan (scan ->
join -> filter -> aggregate order) and produce two candidates from that
ordering — the second of the two prompt strategies the parent spec's §20
names for diversity.
"""

from __future__ import annotations

from typing import ClassVar

from pydantic import ValidationError

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import ChatProviderError, GenerationError
from genql.domain.ports.chat_provider import ChatProvider
from genql.repositories.query.candidate_prompt import (
    render_examples,
    render_link,
    render_schema_conventions,
)
from genql.repositories.query.decomposition_strategy import TwoVariantResponse
from genql.repositories.query.registry import CANDIDATE_STRATEGIES


def build_execution_plan_prompt(
    plan: QueryPlan,
    links: tuple[SchemaLink, ...],
    violations: tuple[GuardrailViolation, ...],
    examples: tuple[AmbiguityExample, ...],
) -> str:
    catalog = "\n".join(render_link(link) for link in links)
    sections = [
        "Reason about the plan below the way a PostgreSQL execution plan "
        "would order it — scan, then join, then filter, then aggregate — "
        "and produce TWO candidate SELECT statements from that ordering, "
        "each representing a genuinely different plausible interpretation "
        "of the question.",
        f"Question:\n{plan.question}",
        f"Plan:\n{plan.plan_text}",
        f"Available objects (reference them as schema.object):\n{catalog}",
        render_schema_conventions(links),
        (
            "Rules:\n"
            "- Each variant is a single SELECT (a leading WITH is fine).\n"
            "- Reference only the objects listed above, schema-qualified.\n"
            "- Include an explicit LIMIT in each variant.\n"
            "- Return `variant_1` and `variant_2`, each raw SQL with no "
            "markdown fence and no commentary."
        ),
    ]
    if violations:
        rendered = "\n".join(f"- {v.rule_name}: {v.message}" for v in violations)
        sections.append(f"The previous attempt was rejected:\n{rendered}")
    sections.append(render_examples(examples))
    return "\n\n".join(s for s in sections if s)


@CANDIDATE_STRATEGIES.register("execution_plan")
class ExecutionPlanStrategy:
    variant_count: ClassVar[int] = 2

    def __init__(self, chat: ChatProvider) -> None:
        self._chat = chat

    def generate_variants(
        self,
        plan: QueryPlan,
        links: tuple[SchemaLink, ...],
        violations: tuple[GuardrailViolation, ...],
        examples: tuple[AmbiguityExample, ...],
    ) -> tuple[SqlCandidate, ...]:
        prompt = build_execution_plan_prompt(plan, links, violations, examples)
        try:
            response = self._chat.complete(prompt, TwoVariantResponse)
        except (ChatProviderError, ValidationError) as exc:
            raise GenerationError(
                f"execution_plan strategy failed to generate SQL for {plan.question!r}: {exc}"
            ) from exc
        variants = (response.variant_1.strip(), response.variant_2.strip())
        if not all(variants):
            raise GenerationError(
                f"the execution_plan strategy returned an empty variant for {plan.question!r}"
            )
        return tuple(SqlCandidate(sql=v, plan=plan) for v in variants)
