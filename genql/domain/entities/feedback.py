"""One rating on one turn, optionally with the SQL the user would have wanted.

Kept in GenQL's own Postgres because the parent spec's §2 warns that feedback
living outside the database becomes an ungoverned shadow data repository. It
is captured only — nothing retrieves it yet, and the corrected SQL is stored
so that a later phase can index it without re-collecting anything.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


class Feedback(BaseModel):
    model_config = ConfigDict(frozen=True)

    thread_id: str
    rating: Literal["good", "bad"]
    corrected_sql: str | None = None
    comment: str | None = None
