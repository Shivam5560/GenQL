"""The wire contract for `POST /queries/{thread_id}/feedback`."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class FeedbackRequest(BaseModel):
    rating: Literal["good", "bad"]
    corrected_sql: str | None = None
    comment: str | None = None
