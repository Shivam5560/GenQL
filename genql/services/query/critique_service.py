"""Combines a deterministic check with one LLM judgment call, per the parent
spec's §9 stage 9 and this phase's §1: the "database signals" — column
existence, type compatibility — are already fully determined by
SchemaLink.column_names, so checking them needs sqlglot, not a model call.
Join validity and plan-alignment are judgment calls a script cannot make, so
one ChatProvider.complete call scores every surviving candidate at once,
folding in the deterministic findings as input rather than a second round
trip.

Per Deviation 7, a ChatProviderError from the model call is NOT wrapped into
a stage-specific error here — it propagates as-is, matching the spec's own
Risk-section wording that this phase does not carve out an exception for
critique's or probing's provider failures.
"""

from __future__ import annotations

from typing import Literal

import sqlglot
from pydantic import BaseModel, ConfigDict
from sqlglot import exp
from sqlglot.errors import ParseError

from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.defect import Defect
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.ports.chat_provider import ChatProvider


class DefectResponse(BaseModel):
    """`severity` is typed exactly like `Defect.severity` (a Literal, not a
    bare str) so a malformed value fails INSIDE `ChatProvider.complete` —
    already converted to a `ChatProviderError` there — rather than later, as
    a bare `pydantic.ValidationError` escaping `Defect(...)` construction with
    no GenqlError wrapper to catch it."""

    model_config = ConfigDict(frozen=True)

    dimension: str | None = None
    severity: Literal["fatal", "repairable", "advisory"]
    message: str


class CandidateCritiqueResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_index: int
    defects: tuple[DefectResponse, ...] = ()
    score: float


class CritiqueBatchResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    reports: tuple[CandidateCritiqueResponse, ...]


def build_critique_prompt(
    plan: QueryPlan,
    candidates: tuple[SqlCandidate, ...],
    validated_sqls: tuple[str, ...],
    deterministic: list[tuple[Defect, ...]],
) -> str:
    rendered = []
    for i, sql in enumerate(validated_sqls):
        found = "; ".join(d.message for d in deterministic[i]) or "none"
        rendered.append(f"Candidate {i}:\n{sql}\nDeterministic findings: {found}")
    return "\n\n".join(
        [
            "Judge every candidate SQL statement below against the plan. For "
            "each, name any join-validity or plan-alignment defects beyond "
            "the deterministic findings already listed, and score it 0-1 for "
            "overall confidence it correctly answers the question.",
            f"Question:\n{plan.question}",
            f"Plan:\n{plan.plan_text}",
            "\n\n".join(rendered),
            (
                "Rules:\n"
                "- Return `reports`, one entry per candidate index.\n"
                "- Each defect names `severity` as exactly one of "
                "'fatal', 'repairable', or 'advisory'.\n"
                "- `dimension` is null unless the defect reflects a specific "
                "contested interpretation (entity, metric, time_range, "
                "grain, filter, or comparison_baseline)."
            ),
        ]
    )


class CritiqueService:
    def __init__(self, chat: ChatProvider) -> None:
        self._chat = chat

    def critique(
        self,
        plan: QueryPlan,
        candidates: tuple[SqlCandidate, ...],
        validated_sqls: tuple[str, ...],
        links: tuple[SchemaLink, ...],
    ) -> tuple[CritiqueReport, ...]:
        deterministic = [self._deterministic_defects(sql, links) for sql in validated_sqls]
        prompt = build_critique_prompt(plan, candidates, validated_sqls, deterministic)
        response = self._chat.complete(prompt, CritiqueBatchResponse)
        by_index = {r.candidate_index: r for r in response.reports}

        reports = []
        for i in range(len(candidates)):
            found = by_index.get(i)
            model_defects = tuple(
                Defect(dimension=d.dimension, severity=d.severity, message=d.message)
                for d in (found.defects if found else ())
            )
            score = found.score if found else 0.0
            reports.append(
                CritiqueReport(
                    candidate_index=i, defects=deterministic[i] + model_defects, score=score
                )
            )
        return tuple(reports)

    @staticmethod
    def _deterministic_defects(sql: str, links: tuple[SchemaLink, ...]) -> tuple[Defect, ...]:
        known_columns = {c for link in links for c in link.column_names}
        if not known_columns:
            return ()
        try:
            expression = sqlglot.parse_one(sql, dialect="postgres")
        except ParseError:
            # StaticValidationService already guarantees sql parses; this is
            # defence in depth, not a path any current caller can reach.
            return ()
        # `find_all(exp.Column)` returns every column-shaped identifier in the
        # tree, including SELECT-list aliases referenced from ORDER BY/GROUP BY
        # and CTE/derived-table names used as a column source — neither is a
        # base-table column that could be "unknown" against SchemaLink. Without
        # excluding them, `SELECT COUNT(*) AS n ... ORDER BY n` flags `n`
        # itself, which is every top-N query.
        aliases = {a.alias for a in expression.find_all(exp.Alias) if a.alias}
        aliases |= {t.alias_or_name for t in expression.find_all(exp.TableAlias) if t.alias_or_name}
        aliases |= {c.alias_or_name for c in expression.find_all(exp.CTE) if c.alias_or_name}
        referenced = {col.name for col in expression.find_all(exp.Column)}
        unknown = sorted(referenced - known_columns - aliases)
        # `known_columns` is only the retrieved objects' columns (schema_linking
        # caps retrieval at search_top_k), so a legitimate join to an object
        # outside that window also looks "unknown" here. That signal is real
        # enough to surface to the model but not proven enough to alone kill a
        # candidate, so it is repairable rather than fatal — only the LLM half
        # of critique, which sees the full plan, may still score it fatal.
        return tuple(
            Defect(
                dimension=None, severity="repairable", message=f"references unknown column {col!r}"
            )
            for col in unknown
        )
