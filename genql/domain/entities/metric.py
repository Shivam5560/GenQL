"""A YAML-authored business metric: a named SQL expression at a stated
grain. Always provenance=YAML in Phase 4 — nothing else proposes a metric."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from genql.domain.value_objects.provenance import Provenance


class Metric(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasource_name: str
    name: str
    sql_expression: str
    grain: str
    unit: str | None = None
    default_filters: dict[str, str] = Field(default_factory=dict)
    provenance: Provenance = Provenance.YAML
