"""Runs discovery steps in order, resumably.

Early steps such as profiling are expensive and need not be repeated when
iterating on later ones, so the runner supports starting from a named step.
"""

from __future__ import annotations

from collections.abc import Sequence

import structlog

from genql.domain.errors import UnknownDiscoveryStepError
from genql.domain.ports.discovery_step import DiscoveryContext, DiscoveryStep, StepResult
from genql.domain.ports.schema_registration_repository import SchemaRegistrationRepository
from genql.domain.value_objects.query_scope import QueryScope
from genql.domain.value_objects.scope_run_result import ScopeRunResult

_log = structlog.get_logger(__name__)


class DiscoveryRunner:
    def __init__(
        self, steps: Sequence[DiscoveryStep], registrations: SchemaRegistrationRepository
    ) -> None:
        self._steps = list(steps)
        self._registrations = registrations

    def run(self, ctx: DiscoveryContext, start_from: str | None = None) -> list[StepResult]:
        results: list[StepResult] = []
        for step in self._select(start_from):
            _log.info("discovery.step.start", step=step.name, schema=ctx.schema_name)
            result = step.run(ctx)
            results.append(result)
            _log.info(
                "discovery.step.end",
                step=step.name,
                succeeded=result.succeeded,
                records=result.records_written,
            )
            if not result.succeeded:
                break
        return results

    def _select(self, start_from: str | None) -> list[DiscoveryStep]:
        if start_from is None:
            return self._steps
        names = [s.name for s in self._steps]
        if start_from not in names:
            raise UnknownDiscoveryStepError(start_from, names)
        return self._steps[names.index(start_from) :]

    def run_scope(
        self, scope: QueryScope, sample_limit: int, start_from: str | None = None
    ) -> list[ScopeRunResult]:
        """Run the step sequence once per schema.

        One schema failing must not abandon the rest of the scope: a broken
        permission on one schema is not a reason to skip the other eleven.
        `last_discovered_at` is stamped only for schemas that finished cleanly,
        so the timestamp means what it says.
        """
        outcomes: list[ScopeRunResult] = []
        for ref in scope.refs():
            ctx = DiscoveryContext(
                datasource_name=ref.datasource_name,
                schema_name=ref.schema_name,
                sample_limit=sample_limit,
            )
            results = self.run(ctx, start_from=start_from)
            outcome = ScopeRunResult(ref=ref, results=tuple(results))
            if outcome.succeeded:
                self._registrations.mark_discovered(ref)
            outcomes.append(outcome)
        return outcomes
