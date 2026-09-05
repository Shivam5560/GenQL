"""A table, view, or materialized view in the target warehouse."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.value_objects.object_type import ObjectType


class DatabaseObject(BaseModel):
    model_config = ConfigDict(frozen=True)

    schema_name: str
    object_name: str
    object_type: ObjectType
    row_estimate: int | None = None

    @property
    def qualified_name(self) -> str:
        return f"{self.schema_name}.{self.object_name}"
