"""A single column of a database object."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Column(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasource_name: str
    schema_name: str
    object_name: str
    column_name: str
    ordinal: int
    data_type: str
    is_nullable: bool
    is_primary_key: bool = False

    @property
    def qualified_name(self) -> str:
        return f"{self.datasource_name}.{self.schema_name}.{self.object_name}.{self.column_name}"
