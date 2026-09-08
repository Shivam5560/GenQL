"""One critique finding against one candidate.

`dimension` is `str | None`, not a `Literal[*AMBIGUITY_DIMENSIONS]`: a
deterministic column/table check has no ambiguity dimension to name (it is a
plain correctness defect), and the LLM half of critique is asked to name one
only when the defect actually reflects a contested interpretation.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Defect(BaseModel):
    model_config = ConfigDict(frozen=True)

    dimension: str | None
    severity: Literal["fatal", "repairable", "advisory"]
    message: str
