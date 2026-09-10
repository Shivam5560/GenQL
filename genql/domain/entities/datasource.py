"""A registered connection to a warehouse GenQL may discover.

A datasource says where its warehouse is in one of two ways, and carries
whichever one it was registered with.

`host`/`port`/`database`/`username` plus `password_ciphertext` is what the
connect form produces: the printable half is stored in the clear so the UI can
say what the datasource points at, and only the password is encrypted. This is
the path every datasource registered through the API takes.

`dsn_env_var` is the older path, kept working rather than migrated away: it
holds the NAME of an environment variable whose value is a whole DSN, read
from the process environment at connect time. Datasources created before
credentials could be stored — `local`, and anything the CLI registered — still
resolve through it.

Exactly one of the two is populated. `password_ciphertext` never leaves the
process that decrypts it: DatasourceDto does not carry it, and neither does
any log line, because nothing here renders a Datasource whole.

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
    dsn_env_var: str | None = None
    host: str | None = None
    port: int | None = None
    database: str | None = None
    username: str | None = None
    password_ciphertext: str | None = None
    options: str | None = None
    description: str | None = None
    enabled: bool = True

    @property
    def endpoint(self) -> str | None:
        """`host:port/database`, or None for an env-var datasource.

        What the datasources page prints under the name. Deliberately excludes
        the username: it is stored, but showing it on a shared screen buys
        nothing the host and database do not already say.
        """
        if not self.host:
            return None
        port = f":{self.port}" if self.port else ""
        database = f"/{self.database}" if self.database else ""
        return f"{self.host}{port}{database}"
