"""A registered connection to a warehouse GenQL may discover.

`dsn_env_var` holds the NAME of an environment variable, never a connection
string. The DSN is read from the process environment at connect time, so
warehouse credentials never enter the semantic store and a dump of that store
is safe to share.

`dialect` is a free-text registry key rather than an enum: an enum would have
to be edited to add a dialect, which is the modification the registry exists to
avoid.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class Datasource(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    dialect: str
    dsn_env_var: str
    description: str | None = None
    enabled: bool = True
