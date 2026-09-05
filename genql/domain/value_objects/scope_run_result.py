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
        return all(r.succeeded for r in self.results)
