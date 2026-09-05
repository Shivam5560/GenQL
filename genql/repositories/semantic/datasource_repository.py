"""Persists registered datasources.

Note what is NOT here: a DSN. The row carries the name of an environment
variable and nothing else, so the semantic store never holds a warehouse
credential.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Connection, Engine, text

from genql.domain.entities.datasource import Datasource
from genql.domain.errors import DuplicateDatasourceError, UnknownDatasourceError

_INSERT = text("""
    INSERT INTO genql.genql_datasource (name, dialect, dsn_env_var, description, enabled)
    VALUES (:name, :dialect, :dsn_env_var, :description, :enabled)
    ON CONFLICT (name) DO NOTHING
    RETURNING name
""")

_SELECT_ONE = text("""
    SELECT name, dialect, dsn_env_var, description, enabled
    FROM genql.genql_datasource WHERE name = :name
""")

_SELECT_ALL = text("""
    SELECT name, dialect, dsn_env_var, description, enabled
    FROM genql.genql_datasource
    WHERE (NOT :enabled_only) OR enabled
    ORDER BY name
""")

_SELECT_NAMES = text("SELECT name FROM genql.genql_datasource ORDER BY name")

_DELETE = text("DELETE FROM genql.genql_datasource WHERE name = :name RETURNING name")


class PostgresDatasourceRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, datasource: Datasource) -> None:
        with self._engine.begin() as conn:
            inserted = conn.execute(_INSERT, datasource.model_dump(mode="json")).scalar()
        if inserted is None:
            raise DuplicateDatasourceError(datasource.name)

    def get(self, name: str) -> Datasource:
        with self._engine.connect() as conn:
            row = conn.execute(_SELECT_ONE, {"name": name}).one_or_none()
            if row is None:
                raise UnknownDatasourceError(name, self._names(conn))
        return Datasource.model_validate(row._mapping)  # noqa: SLF001 - Row mapping is public API

    def list_all(self, enabled_only: bool = False) -> Sequence[Datasource]:
        with self._engine.connect() as conn:
            rows = conn.execute(_SELECT_ALL, {"enabled_only": enabled_only}).all()
        return [Datasource.model_validate(r._mapping) for r in rows]  # noqa: SLF001

    def remove(self, name: str) -> None:
        with self._engine.begin() as conn:
            deleted = conn.execute(_DELETE, {"name": name}).scalar()
            if deleted is None:
                raise UnknownDatasourceError(name, self._names(conn))

    @staticmethod
    def _names(conn: Connection) -> list[str]:
        return [r[0] for r in conn.execute(_SELECT_NAMES).all()]
