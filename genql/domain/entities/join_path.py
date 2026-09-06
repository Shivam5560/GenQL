"""A mined route between two objects that FK edges alone connect indirectly."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.value_objects.provenance import Provenance


class JoinPath(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasource_name: str
    schema_name: str
    source_object: str
    target_object: str
    path: tuple[str, ...]
    weight: float
    provenance: Provenance = Provenance.DISCOVERED
