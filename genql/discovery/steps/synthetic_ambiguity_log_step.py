"""Registered last (after object_profiling in registration order). Domain
naming (`genql graph domains`) is not itself a DiscoveryStep — it is invoked
by its own CLI command outside DiscoveryRunner entirely (Deviation 6) — so a
first `genql discover` run reaches this step before any domain exists and
correctly reports zero records, not a failure. Re-running
`genql discover --start-from synthetic_ambiguity_log` after `genql graph
domains` is the intended path to populate it for real.
"""

from __future__ import annotations

from typing import ClassVar

from genql.discovery.registry import DISCOVERY_STEPS
from genql.domain.errors import DiscoveryError
from genql.domain.ports.discovery_step import DiscoveryContext, StepResult
from genql.services.discovery.synthetic_ambiguity_log_service import SyntheticAmbiguityLogService


@DISCOVERY_STEPS.register("synthetic_ambiguity_log")
class SyntheticAmbiguityLogStep:
    name: ClassVar[str] = "synthetic_ambiguity_log"

    def __init__(self, service: SyntheticAmbiguityLogService) -> None:
        self._service = service

    def run(self, ctx: DiscoveryContext) -> StepResult:
        try:
            written = self._service.generate(ctx.datasource_name)
        except DiscoveryError as exc:
            return StepResult(
                step_name=self.name, succeeded=False, records_written=0, message=str(exc)
            )
        return StepResult(
            step_name=self.name,
            succeeded=True,
            records_written=written,
            message=f"{written} ambiguity examples written",
        )
