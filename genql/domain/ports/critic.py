"""Scores every surviving candidate against the plan and each other.

`validated_sqls[i]` is the qualified statement for `candidates[i]` — the
deterministic column/table check runs against this, not `candidates[i].sql`,
since qualification can rewrite references a pre-qualification check would
misjudge.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate


@runtime_checkable
class Critic(Protocol):
    def critique(
        self,
        plan: QueryPlan,
        candidates: tuple[SqlCandidate, ...],
        validated_sqls: tuple[str, ...],
        links: tuple[SchemaLink, ...],
    ) -> tuple[CritiqueReport, ...]: ...
