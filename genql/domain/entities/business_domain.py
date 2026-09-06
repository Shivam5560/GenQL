"""A named business domain: one cluster of objects, given a name and a
description. Named BusinessDomain, not Domain — the latter collides with the
architecture's own domain/ layer name."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.value_objects.provenance import Provenance


class BusinessDomain(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasource_name: str
    domain_id: int | None = None
    name: str
    description: str
    provenance: Provenance = Provenance.LLM
