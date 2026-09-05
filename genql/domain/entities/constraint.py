"""A primary key, foreign key, or unique constraint."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genql.domain.value_objects.constraint_type import ConstraintType


class Constraint(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasource_name: str
    schema_name: str
    object_name: str
    constraint_name: str
    constraint_type: ConstraintType
    definition: str
    referenced_object_name: str | None = None
    column_names: tuple[str, ...] = ()
    referenced_column_names: tuple[str, ...] = ()
