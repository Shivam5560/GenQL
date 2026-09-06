"""The natural-language plan produced before any SQL exists.

The parent spec's §9 stage 6 is the technique behind Oracle's Archer result:
an inspectable plan that later stages check the SQL against. Phase 5 has no
critique stage yet, so the plan's immediate job is grounding — it names the
objects the candidate is allowed to be about.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class QueryPlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: str
    plan_text: str
    referenced_objects: tuple[str, ...]
