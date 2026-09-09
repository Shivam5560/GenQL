"""Designs the targeted queries that let the data resolve a critique
disagreement. Only designs them — validating and executing probe_sql reuses
StaticValidationService and GuardedExecutionService unchanged, one layer up in
AmbiguityProbingService."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.ambiguity_probe import AmbiguityProbe
from genql.domain.entities.critique_report import CritiqueReport
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.sql_candidate import SqlCandidate


@runtime_checkable
class ProbeDesigner(Protocol):
    def design(
        self,
        plan: QueryPlan,
        candidates: tuple[SqlCandidate, ...],
        validated_sqls: tuple[str, ...],
        critiques: tuple[CritiqueReport, ...],
    ) -> tuple[AmbiguityProbe, ...]: ...
