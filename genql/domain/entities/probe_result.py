"""One probe's real result, compared against every candidate's prediction.

`resolved_candidate_index` is None when no prediction matched the real
result — a prediction rendering mismatch (e.g. "42" vs "42.0") rather than a
crash, per this phase's own Risk section: it fails visibly downstream
(selection falls back to critique ranking) rather than raising here.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.ambiguity_probe import AmbiguityProbe


class ProbeResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    probe: AmbiguityProbe
    actual_result: str
    resolved_candidate_index: int | None = None
