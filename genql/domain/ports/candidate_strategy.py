"""One way of turning a plan into SQL variants.

`variant_count` is fixed per strategy rather than a runtime parameter, since
each strategy's prompt is built around producing exactly that many structured
variants from one ChatProvider.complete call.
"""

from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate


@runtime_checkable
class CandidateGenerationStrategy(Protocol):
    variant_count: ClassVar[int]

    def generate_variants(
        self,
        plan: QueryPlan,
        links: tuple[SchemaLink, ...],
        violations: tuple[GuardrailViolation, ...],
        examples: tuple[AmbiguityExample, ...],
    ) -> tuple[SqlCandidate, ...]: ...
