"""LLM-grounded (or YAML-overridden) description of one database object."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from genql.domain.value_objects.provenance import Provenance


class ObjectEnrichment(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasource_name: str
    schema_name: str
    object_name: str
    description: str
    business_alias: str | None = None
    provenance: Provenance = Provenance.LLM
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    embedding: tuple[float, ...] | None = None

    @property
    def qualified_name(self) -> str:
        return f"{self.datasource_name}.{self.schema_name}.{self.object_name}"
