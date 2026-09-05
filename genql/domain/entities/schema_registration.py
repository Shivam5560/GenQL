"""A schema of a datasource that GenQL has been told to manage.

Registration is explicit: discovery writes catalog rows that carry a foreign
key to this table, so a schema must be registered before it can be discovered.
That is what makes `genql schema list` an accurate inventory rather than a
side effect of whatever anyone last scanned.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from genql.domain.value_objects.schema_ref import SchemaRef


class SchemaRegistration(BaseModel):
    model_config = ConfigDict(frozen=True)

    datasource_name: str
    schema_name: str
    description: str | None = None
    enabled: bool = True
    last_discovered_at: datetime | None = None

    @property
    def ref(self) -> SchemaRef:
        return SchemaRef(datasource_name=self.datasource_name, schema_name=self.schema_name)
