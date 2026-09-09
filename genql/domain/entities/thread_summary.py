"""The sidebar's row and the ownership check's source of truth. `title` is
the first question, truncated — good enough without a summarisation pass,
and consistent with how the mockups render thread names."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ThreadSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    thread_id: str
    user_id: str
    datasource_name: str
    title: str
    created_at: datetime
    last_active_at: datetime
