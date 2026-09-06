"""The one shape description/alias/unit enrichment share: a single string
value on one object or column, competing between a discovered/LLM value and
a YAML override. Metric and join-hint enrichment do NOT share this shape
(see Non-goals in the spec) and are handled by their own dedicated code."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from genql.domain.value_objects.provenance import Provenance

EnrichmentKind = Literal["description", "alias", "unit"]


class EnrichmentField(BaseModel):
    model_config = ConfigDict(frozen=True)

    kind: EnrichmentKind
    qualified_name: str
    value: str
    provenance: Provenance
