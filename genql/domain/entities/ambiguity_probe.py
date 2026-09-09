"""One targeted query issued to let the data arbitrate between candidates.

`candidate_predictions` pairs a candidate's index with what its interpretation
predicts the probe will return, rendered as a string up front — comparing the
probe's real result against these predictions is then a lookup
(AmbiguityProbingService), never a second judgment call.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AmbiguityProbe(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimension: str
    probe_sql: str
    candidate_predictions: tuple[tuple[int, str], ...]
