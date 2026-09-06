"""Every `schema.object` one datasource has in the semantic store.

Lowercased on the way out because the only consumer is the object allowlist,
which compares against identifiers sqlglot has normalized — comparing raw
catalog casing against normalized SQL would reject valid statements.
"""

from __future__ import annotations

from sqlalchemy import Engine, text

_SELECT_OBJECT_NAMES = text("""
    SELECT schema_name, object_name
    FROM genql.genql_object
    WHERE datasource_name = :datasource_name
""")


class PostgresObjectNameReader:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def read_object_names(self, datasource_name: str) -> frozenset[str]:
        with self._engine.connect() as conn:
            rows = conn.execute(_SELECT_OBJECT_NAMES, {"datasource_name": datasource_name}).all()
        return frozenset(f"{r.schema_name}.{r.object_name}".lower() for r in rows)
