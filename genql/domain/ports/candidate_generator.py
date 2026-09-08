"""Produces one candidate on the non-contested path, or several on the
contested path.

`domain_id` lets the implementation fetch few-shot ambiguity examples scoped
to the right domain; `contested` and `escalated` are read from QueryState by
CandidateGenerationNode and passed straight through, so this port carries them
as keyword-only rather than deriving them itself.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate


@runtime_checkable
class CandidateGenerator(Protocol):
    def generate(  # noqa: PLR0913, PLR0917 - matches CandidateGenerationService's signature
        self,
        plan: QueryPlan,
        links: tuple[SchemaLink, ...],
        violations: tuple[GuardrailViolation, ...] = (),
        *,
        domain_id: int | None = None,
        contested: bool = False,
        escalated: bool = False,
    ) -> tuple[SqlCandidate, ...]: ...
