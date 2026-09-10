"""Where a warehouse lives and who to connect as.

This is the form a person fills in — host, port, database, user, password —
not the DSN string those five compose into. Keeping them apart matters at
exactly one point: `host`, `port`, `database` and `username` are printable and
are stored in the clear so the datasources page can say what it is pointed at,
while `password` is the only field that is a secret. A single opaque DSN
column would have forced all five into ciphertext and left the UI with nothing
to show.

`options` carries the driver query string (`sslmode=require` and friends) as
already-encoded text, because the set of legal options is the driver's
business and enumerating them here would mean editing this file every time a
warehouse wants one more.

`render_dsn` lives here rather than in an infrastructure helper because
DatasourceService — which may not import sqlalchemy or infrastructure — is the
caller. It is deliberately string assembly over stdlib quoting rather than
`sqlalchemy.URL`: a password containing `@` or `/` is the common case that
breaks naive concatenation, and `quote` is the whole fix.
"""

from __future__ import annotations

from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, Field


class DatasourceConnection(BaseModel):
    model_config = ConfigDict(frozen=True)

    host: str
    port: int = Field(gt=0, le=65535)
    database: str
    username: str
    password: str = ""
    options: str | None = None

    def render_dsn(self, scheme: str) -> str:
        """`scheme` is the SQLAlchemy driver prefix — `postgresql+psycopg`."""
        credentials = quote(self.username, safe="")
        if self.password:
            credentials += f":{quote(self.password, safe='')}"
        dsn = f"{scheme}://{credentials}@{self.host}:{self.port}/{quote(self.database, safe='')}"
        return f"{dsn}?{self.options}" if self.options else dsn
