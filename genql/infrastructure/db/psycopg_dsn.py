"""Convert GenQL's SQLAlchemy URL into the libpq DSN psycopg wants.

Pure string work, no I/O, no driver import — so it stays a plain function and
is unit-testable without a database. Rejecting a non-Postgres URL rather than
passing it through is deliberate: everything that calls this is about to open a
psycopg connection, and failing here names the setting, while failing there
names a socket.
"""

from __future__ import annotations

import re

_DRIVER_TOKEN = re.compile(r"^(postgresql|postgres)\+[A-Za-z0-9_]+://")


def to_libpq_dsn(url: str) -> str:
    if not url.startswith(("postgresql://", "postgres://")) and not _DRIVER_TOKEN.match(url):
        raise ValueError(
            f"{url!r} is not a postgres URL; GENQL_SEMANTIC_DSN must name GenQL's "
            "own PostgreSQL database"
        )
    return _DRIVER_TOKEN.sub(r"\1://", url)
