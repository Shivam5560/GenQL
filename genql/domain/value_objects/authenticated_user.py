"""What a verified GoTrue JWT tells GenQL about the caller. Built purely
from JWT claims — no database round trip."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class AuthenticatedUser(BaseModel):
    model_config = ConfigDict(frozen=True)

    user_id: str
    email: str
