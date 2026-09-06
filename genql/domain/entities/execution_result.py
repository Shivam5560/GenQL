"""Rows read back from a guarded execution.

`truncated` is set by the executor when the warehouse returned more rows than
the row cap allowed, so the CLI can say so rather than silently presenting a
partial answer as a whole one.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class ExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    row_count: int
    truncated: bool
