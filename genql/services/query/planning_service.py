"""Produces the natural-language plan before any SQL exists.

The parent spec's §9 stage 6, and the technique behind Oracle's Archer
result: an explicit, inspectable plan that later stages check the SQL
against. Phase 5 has no critique stage yet, so the plan's job here is
grounding — it fixes which objects the candidate is allowed to be about
before the generator has a chance to invent one.

Refusing to plan with zero links is deliberate: an ungrounded plan is exactly
the hallucination this stage exists to prevent, and calling the provider to
produce one would cost money to obtain a worse answer.

Takes `answers` — the ambiguity gate's (dimension, answer) pairs — and renders
them into the prompt. Before this, a clarifying answer was recorded in
`QueryState.clarifications` only to satisfy the gate's own loop and was never
read again: planning and every stage after it saw only the original raw
question, so "no date filter" or "all three channels" never reached the SQL.
The observed failure mode was not "the answer is ignored" in an obvious way —
it was worse: with no explicit instruction, the model still had to decide
*something* for an under-specified dimension, and it silently picked a
plausible-looking default (a narrow date window) that matched neither the
user's actual answer nor an honest "no filter." Stating the answer in the plan
prompt, the same way the gate's own prompt already states prior answers back
to itself, is what makes the plan actually binding on what follows it.
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
    parts = [f"- {link.schema_qualified_name}"]
    if link.column_names:
        parts.append(f"    columns: {', '.join(link.column_names)}")
    if link.join_paths:
        parts.append(f"    join paths: {', '.join(link.join_paths)}")
    if link.metric_names:
        parts.append(f"    metrics: {', '.join(link.metric_names)}")
    return "\n".join(parts)


def build_planning_prompt(
    question: str,
    links: tuple[SchemaLink, ...],
    answers: tuple[tuple[str, str], ...] = (),
    assumed: tuple[tuple[str, str], ...] = (),
) -> str:
    catalog = "\n".join(_render_link(link) for link in links)
    context = (
        "\n".join(f"- {dimension}: {answer}" for dimension, answer in answers) if answers else ""
    )
    assumptions = (
        "\n".join(f"- {dimension}: {value}" for dimension, value in assumed) if assumed else ""
    )
    sections = [
        "You are planning how to answer an analytical question against a data warehouse.\n"
        "Write the plan in prose. Do NOT write SQL.\n\n"
        f"Question:\n{question}",
    ]
    if context:
        sections.append(
            "The user was already asked to clarify the following, and answered:\n"
            f"{context}\n\n"
            "Every one of these answers is binding. If an answer says a dimension has no "
            'restriction ("all time", "every channel", "no filter"), the plan must say '
            "so explicitly and apply none — do not substitute a plausible-looking default "
            "in its place. Do not re-decide a dimension the user already answered."
        )
    if assumptions:
        sections.append(
            "The following were NOT asked. They are this datasource's standing "
            "defaults and the best reading of the question where it was silent:\n"
            f"{assumptions}\n\n"
            "Apply them exactly as stated — they are binding in the same way an "
            "answer is, and inventing a different value for one of these "
            "dimensions is an error. State each one in the plan as an "
            "assumption, so a reader can see what was decided on their behalf."
        )
    sections.append(f"Available objects:\n{catalog}")
    sections.append(
        "Rules:\n"
        "- Use only the objects listed above. Naming anything else is an error.\n"
        "- Join only along the join paths listed above.\n"
        "- State the grain of the answer, the filters, and the aggregation.\n"
        "- Return `plan_text` (the prose plan) and `referenced_objects` (the fully "
        "qualified names, exactly as listed above, that the plan actually uses)."
    )
    return "\n\n".join(sections)


class PlanningService:
    def __init__(self, chat: ChatProvider) -> None:
        self._chat = chat

    def plan(
        self,
        question: str,
        links: tuple[SchemaLink, ...],
        answers: tuple[tuple[str, str], ...] = (),
        assumed: tuple[tuple[str, str], ...] = (),
    ) -> QueryPlan:
        if not links:
            raise PlanningError(f"cannot plan {question!r} with no schema links")
        try:
            response = self._chat.complete(
                build_planning_prompt(question, links, answers, assumed), PlanResponse
            )
        except (ChatProviderError, ValidationError) as exc:
            raise PlanningError(f"failed to plan {question!r}: {exc}") from exc
        return QueryPlan(
            question=question,
            plan_text=response.plan_text,
            referenced_objects=tuple(response.referenced_objects),
        )
