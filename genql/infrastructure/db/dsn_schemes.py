"""Which SQLAlchemy driver each warehouse dialect connects through.

A plain mapping rather than a Registry: a driver scheme is a five-character
string, not an implementation to construct, and the registry's whole value —
`create(key, **kwargs)` — buys nothing for a lookup. It is keyed by the same
dialect strings CATALOG_READERS is keyed by, so adding a dialect means adding
its reader, its profile reader, and one line here.

`postgresql+psycopg` is psycopg 3, matching the driver this project depends
on; `postgresql+psycopg2` would silently pick a driver that is not installed.

A plain dict rather than MappingProxyType because dependency-injector deep-copies
every declarative provider's arguments and a mapping proxy is not copyable.
Both readers take a copy of it on the way in, so the shared instance is never
the one being read from.
"""

from __future__ import annotations

DSN_SCHEMES: dict[str, str] = {"postgres": "postgresql+psycopg"}
