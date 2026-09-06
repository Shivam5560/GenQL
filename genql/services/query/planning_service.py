"""Produces the natural-language plan before any SQL exists.

The parent spec's §9 stage 6, and the technique behind Oracle's Archer
result: an explicit, inspectable plan that later stages check the SQL
against. Phase 5 has no critique stage yet, so the plan's job here is
grounding — it fixes which objects the candidate is allowed to be about
before the generator has a chance to invent one.

Refusing to plan with zero links is deliberate: an ungrounded plan is exactly
the hallucination this stage exists to prevent, and calling the provider to
produce one would cost money to obtain a worse answer.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, ValidationError

from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.errors import ChatProviderError, PlanningError
from genql.domain.ports.chat_provider import ChatProvider


class PlanResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    plan_text: str
    referenced_objects: list[str]


def _render_link(link: SchemaLink) -> str:
    parts = [f"- {link.object_qualified_name}"]
    if link.column_names:
        parts.append(f"    columns: {', '.join(link.column_names)}")
    if link.join_paths:
        parts.append(f"    join paths: {', '.join(link.join_paths)}")
    if link.metric_names:
        parts.append(f"    metrics: {', '.join(link.metric_names)}")
    return "\n".join(parts)


def build_planning_prompt(question: str, links: tuple[SchemaLink, ...]) -> str:
    catalog = "\n".join(_render_link(link) for link in links)
    return (
        "You are planning how to answer an analytical question against a data warehouse.\n"
        "Write the plan in prose. Do NOT write SQL.\n\n"
        f"Question:\n{question}\n\n"
        f"Available objects:\n{catalog}\n\n"
        "Rules:\n"
        "- Use only the objects listed above. Naming anything else is an error.\n"
        "- Join only along the join paths listed above.\n"
        "- State the grain of the answer, the filters, and the aggregation.\n"
        "- Return `plan_text` (the prose plan) and `referenced_objects` (the fully "
        "qualified names, exactly as listed above, that the plan actually uses)."
    )


class PlanningService:
    def __init__(self, chat: ChatProvider) -> None:
        self._chat = chat

    def plan(self, question: str, links: tuple[SchemaLink, ...]) -> QueryPlan:
        if not links:
            raise PlanningError(f"cannot plan {question!r} with no schema links")
        try:
            response = self._chat.complete(build_planning_prompt(question, links), PlanResponse)
        except (ChatProviderError, ValidationError) as exc:
            raise PlanningError(f"failed to plan {question!r}: {exc}") from exc
        return QueryPlan(
            question=question,
            plan_text=response.plan_text,
            referenced_objects=tuple(response.referenced_objects),
        )
