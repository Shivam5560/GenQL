"""A single column of a database object."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Column(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_name: str
    object_name: str
    column_name: str
    ordinal: int
    data_type: str
    is_nullable: bool
    is_primary_key: bool = False

    @property
    def qualified_name(self) -> str:
        return f"{self.schema_name}.{self.object_name}.{self.column_name}"
