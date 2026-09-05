"""One step of the offline discovery pipeline."""

from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field


class DiscoveryContext(BaseModel):
    """Carries state between discovery steps.

    The field is `schema_name`, not `schema`: Pydantic v2 raises NameError when a
    field shadows an attribute of BaseModel, and `BaseModel.schema()` still exists
    as a deprecated method. It also matches the entities, which all use schema_name.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    schema_name: str
    sample_limit: int = 5
    artifacts: dict[str, object] = Field(default_factory=dict)


class StepResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    step_name: str
    succeeded: bool
    records_written: int
    message: str


@runtime_checkable
class DiscoveryStep(Protocol):
    name: ClassVar[str]

    def run(self, ctx: DiscoveryContext) -> StepResult: ...
