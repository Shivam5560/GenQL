"""Observed statistics for a column.

Sample values are what let a column named TYPE with values
[CREDIT, DEBIT, TRANSFER] be understood as a payment transaction type.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ColumnProfile(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_name: str
    object_name: str
    column_name: str
    distinct_count: int | None = None
    null_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    sample_values: tuple[str, ...] = ()

    @property
    def qualified_name(self) -> str:
        return f"{self.schema_name}.{self.object_name}.{self.column_name}"
