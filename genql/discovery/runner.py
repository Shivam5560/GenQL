"""Runs discovery steps in order, resumably.

Early steps such as profiling are expensive and need not be repeated when
iterating on later ones, so the runner supports starting from a named step.
"""

from __future__ import annotations

from collections.abc import Sequence

import structlog

from genql.domain.ports.discovery_step import DiscoveryContext, DiscoveryStep, StepResult

_log = structlog.get_logger(__name__)


class DiscoveryRunner:
    def __init__(self, steps: Sequence[DiscoveryStep]) -> None:
        self._steps = list(steps)

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
        return self._steps[names.index(start_from) :]
