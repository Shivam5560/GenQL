"""Produces exactly one SQL candidate from a plan and its schema links.

Phase 5 generates one candidate, not N. The parent spec's §9 stage 7 asks for
N candidates representing genuinely different interpretations, but critique,
probing, and selection — the stages that consume the disagreement between
them — are Phase 6. Generating a second candidate with nothing to resolve it
against would be dead work.

`violations` is empty on the first attempt. On the graph's single retry it
carries the previous attempt's guardrail failures, which is the only thing
that makes the retry more than a re-roll of the same dice.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationError

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.errors import ChatProviderError, GenerationError
from genql.domain.ports.chat_provider import ChatProvider


class SqlResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    sql: str


def _render_link(link: SchemaLink) -> str:
    parts = [f"- {link.object_qualified_name}"]
    if link.column_names:
        parts.append(f"    columns: {', '.join(link.column_names)}")
    if link.join_paths:
        parts.append(f"    join paths: {', '.join(link.join_paths)}")
    if link.metric_names:
        parts.append(f"    metrics: {', '.join(link.metric_names)}")
    return "\n".join(parts)


def build_generation_prompt(
    plan: QueryPlan, links: tuple[SchemaLink, ...], violations: tuple[GuardrailViolation, ...]
) -> str:
    catalog = "\n".join(_render_link(link) for link in links)
    sections = [
        "Write one PostgreSQL SELECT statement that carries out the plan below.",
        f"Question:\n{plan.question}",
        f"Plan:\n{plan.plan_text}",
        f"Available objects (reference them as schema.object):\n{catalog}",
        (
            "Rules:\n"
            "- A single SELECT (a leading WITH is fine). No DDL, DML, or DCL.\n"
            "- Reference only the objects listed above, schema-qualified.\n"
            "- Join only along the join paths listed above.\n"
            "- Include an explicit LIMIT.\n"
            "- Return the statement in `sql`, with no markdown fence and no commentary."
        ),
    ]
    if violations:
        rendered = "\n".join(f"- {v.rule_name}: {v.message}" for v in violations)
        sections.append(
            "The previous attempt was rejected by static validation. Fix these and "
            f"do not repeat them:\n{rendered}"
        )
    return "\n\n".join(sections)


class CandidateGenerationService:
    def __init__(self, chat: ChatProvider) -> None:
        self._chat = chat

    def generate(
        self,
        plan: QueryPlan,
        links: tuple[SchemaLink, ...],
        violations: tuple[GuardrailViolation, ...] = (),
    ) -> SqlCandidate:
        if not links:
            raise GenerationError(f"cannot generate SQL for {plan.question!r} with no schema links")
        try:
            response = self._chat.complete(
                build_generation_prompt(plan, links, violations), SqlResponse
            )
        except (ChatProviderError, ValidationError) as exc:
            raise GenerationError(f"failed to generate SQL for {plan.question!r}: {exc}") from exc
        if not response.sql.strip():
            raise GenerationError(
                f"the generator returned an empty statement for {plan.question!r}"
            )
        return SqlCandidate(sql=response.sql.strip(), plan=plan)
