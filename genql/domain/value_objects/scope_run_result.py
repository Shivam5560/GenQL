"""Everything one schema's discovery run produced."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.ports.discovery_step import StepResult
from genql.domain.value_objects.schema_ref import SchemaRef


class ScopeRunResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    ref: SchemaRef
    results: tuple[StepResult, ...]

    @property
    def succeeded(self) -> bool:
        """True only when at least one step ran and every one of them passed.

        `all(())` is True, so without the emptiness guard a run that executed
        no steps at all would look like a success and stamp
        `last_discovered_at` for a schema nothing was discovered from.
        """
        return bool(self.results) and all(r.succeeded for r in self.results)
