"""One object's membership in one business domain."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DomainMember(BaseModel):
    model_config = ConfigDict(frozen=True)

    domain_id: int
    datasource_name: str
    schema_name: str
    object_name: str
    membership_score: float = Field(default=1.0, ge=0.0, le=1.0)
