"""The winning candidate, and which qualified SQL to actually run.

`selected_sql` is the qualified string StaticValidationService produced for
the winning candidate, not `selected.sql` (the pre-repair, pre-qualification
text the generator emitted). Carrying both lets a later stage explain *which
interpretation* won while executing exactly what passed validation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.sql_candidate import SqlCandidate


class CandidateSelection(BaseModel):
    model_config = ConfigDict(frozen=True)

    selected: SqlCandidate
    selected_sql: str
    method: Literal["single_survivor", "probe_resolved", "critique_ranked"]
    rationale: str
