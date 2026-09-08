"""What critique decided about one surviving candidate.

`candidate_index` is the position in the surviving-candidates tuple this
report is about, not a stable identifier: candidates carry no id of their own,
and critique runs once per turn over one fixed tuple, so a position is
unambiguous for that tuple's lifetime.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.defect import Defect


class CritiqueReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_index: int
    defects: tuple[Defect, ...]
    score: float

    @property
    def is_fatal(self) -> bool:
        return any(defect.severity == "fatal" for defect in self.defects)
