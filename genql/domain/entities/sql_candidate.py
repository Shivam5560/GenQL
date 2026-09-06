"""One generated statement, carrying the plan it came from.

Phase 5 generates exactly one candidate per question. The plan travels with
it so a later phase's critique stage can diff SQL against plan without
re-threading both through every signature.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.entities.query_plan import QueryPlan


class SqlCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    sql: str
    plan: QueryPlan
