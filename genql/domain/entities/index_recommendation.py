"""One index GenQL suggests a human create.

The parent spec's §11 is explicit that GenQL never creates an index itself, so
this entity is a report line, not a command. `rationale` is a full sentence
because an operator reading `genql optimizer recommend-indexes` needs to judge
the suggestion, not just apply it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class IndexRecommendation(BaseModel):
    model_config = ConfigDict(frozen=True)

    object_qualified_name: str
    column_name: str
    rationale: str
    supporting_execution_count: int
