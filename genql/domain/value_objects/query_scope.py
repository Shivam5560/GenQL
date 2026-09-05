"""The set of schemas a discovery run or a query addresses.

A scope names exactly ONE datasource. That is the federation decision made
into a type: a scope spanning two datasources is unrepresentable, so no
downstream stage can assume cross-datasource joins work. PostgreSQL joins
across schemas natively, which is why n schemas within one datasource costs
nothing and n datasources would cost an execution layer.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from genql.domain.value_objects.schema_ref import SchemaRef


class QueryScope(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasource_name: str
    schema_names: tuple[str, ...] = Field(min_length=1)

    def refs(self) -> tuple[SchemaRef, ...]:
        return tuple(
            SchemaRef(datasource_name=self.datasource_name, schema_name=name)
            for name in self.schema_names
        )
