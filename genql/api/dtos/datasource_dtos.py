"""The wire contract for `GET /datasources`.

`dsn_env_var` is omitted: it names the environment variable holding a
warehouse credential, and even the variable's name is not something a client
of this API needs or should see.
"""

from __future__ import annotations

from pydantic import BaseModel

from genql.domain.entities.datasource import Datasource


class DatasourceDto(BaseModel):
    name: str
    dialect: str
    description: str | None = None
    enabled: bool = True

    @classmethod
    def from_domain(cls, datasource: Datasource) -> DatasourceDto:
        return cls(
            name=datasource.name,
            dialect=datasource.dialect,
            description=datasource.description,
            enabled=datasource.enabled,
        )
