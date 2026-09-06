"""Runs discovery steps in order, resumably.

Early steps such as profiling are expensive and need not be repeated when
iterating on later ones, so the runner supports starting from a named step.
"""

from __future__ import annotations

from collections.abc import Sequence

import structlog

from genql.domain.errors import GenqlError, UnknownDiscoveryStepError
from genql.domain.ports.discovery_step import DiscoveryContext, DiscoveryStep, StepResult
from genql.domain.ports.schema_registration_repository import SchemaRegistrationRepository
from genql.domain.value_objects.query_scope import QueryScope
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.domain.value_objects.scope_run_result import ScopeRunResult

_log = structlog.get_logger(__name__)


def _failed(step_name: str, exc: Exception) -> StepResult:
    return StepResult(step_name=step_name, succeeded=False, records_written=0, message=str(exc))


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
            # A step reports its own DiscoveryError as a failed StepResult, but
            # anything raised before it reaches its service — resolving the
            # datasource row, reading a DSN out of the environment — is a
            # GenqlError of another branch. Turning it into a failed result
            # here keeps one broken datasource from aborting the whole scope.
            try:
                result = step.run(ctx)
            except GenqlError as exc:
                result = _failed(step.name, exc)
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
        # Validated once, before any schema runs: a mistyped `--start-from` is
        # the caller's error, not one schema's, so it propagates to the CLI
        # rather than being reported n times as n failed schemas.
        self._select(start_from)
        return [self._run_ref(ref, sample_limit, start_from) for ref in scope.refs()]

    def _run_ref(self, ref: SchemaRef, sample_limit: int, start_from: str | None) -> ScopeRunResult:
        ctx = DiscoveryContext(
            datasource_name=ref.datasource_name,
            schema_name=ref.schema_name,
            sample_limit=sample_limit,
        )
        try:
            results = tuple(self.run(ctx, start_from=start_from))
        except GenqlError as exc:
            _log.warning("discovery.scope.schema_failed", schema=ref.qualified_name, error=str(exc))
            return ScopeRunResult(ref=ref, results=(_failed("discovery", exc),))
        outcome = ScopeRunResult(ref=ref, results=results)
        if outcome.succeeded:
            self._registrations.mark_discovered(ref)
        return outcome
