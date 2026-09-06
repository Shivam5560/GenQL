"""Produces one SQL candidate from a plan and its schema links.

`violations` is empty on the first attempt and carries the previous attempt's
guardrail failures on the graph's single retry. Without it the retry would be
handed identical inputs and would have no reason to produce different SQL.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate


@runtime_checkable
class CandidateGenerator(Protocol):
    def generate(
        self,
        plan: QueryPlan,
        links: tuple[SchemaLink, ...],
        violations: tuple[GuardrailViolation, ...] = (),
    ) -> SqlCandidate: ...
