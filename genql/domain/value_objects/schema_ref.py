"""Identifies one schema inside one datasource.

Every catalog row is keyed on this pair. It is a value object rather than two
loose strings so a function signature cannot silently accept them in the wrong
order, and so the pair can key a dict of per-schema results.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SchemaRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasource_name: str
    schema_name: str

    @property
    def qualified_name(self) -> str:
        return f"{self.datasource_name}.{self.schema_name}"
