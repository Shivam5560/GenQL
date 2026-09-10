"""Carries the current trace across a thread boundary.

OpenTelemetry's current span lives in a `contextvars` variable, and
`ThreadPoolExecutor` does not copy context into its workers. Candidate
generation submits one strategy per thread, so without this every strategy's
model call would start a trace of its own and a single turn would arrive at
the collector as several — the one shape that makes counting calls per turn
impossible.

The capture has to happen on the calling thread, which is why this wraps the
strategy at construction time rather than at call time: the factory builds
strategies while the turn's span is still current, and the wrapper re-attaches
that context inside whichever thread ends up running the work.
"""

from __future__ import annotations

from typing import Any

from opentelemetry.context import attach, detach, get_current

from genql.domain.entities.ambiguity_example import AmbiguityExample
from genql.domain.entities.guardrail_violation import GuardrailViolation
from genql.domain.entities.query_plan import QueryPlan
from genql.domain.entities.schema_link import SchemaLink
from genql.domain.entities.sql_candidate import SqlCandidate
from genql.domain.ports.candidate_strategy import CandidateGenerationStrategy


class ContextCarryingStrategy:
    """A CandidateGenerationStrategy that runs inside its creator's trace."""

    def __init__(self, strategy: CandidateGenerationStrategy) -> None:
        self._strategy = strategy
        self._context = get_current()

    @property
    def variant_count(self) -> int:
        """Forwarded, because the service asks the strategy how many it makes."""
        count: int = self._strategy.variant_count
        return count

    def generate_variants(
        self,
        plan: QueryPlan,
        links: tuple[SchemaLink, ...],
        violations: tuple[GuardrailViolation, ...],
        examples: tuple[AmbiguityExample, ...],
    ) -> tuple[SqlCandidate, ...]:
        token = attach(self._context)
        try:
            return self._strategy.generate_variants(plan, links, violations, examples)
        finally:
            detach(token)

    def __getattr__(self, name: str) -> Any:
        """Anything else a strategy exposes belongs to the strategy."""
        return getattr(self._strategy, name)
