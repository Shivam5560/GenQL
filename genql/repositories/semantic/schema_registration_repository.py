"""Persists the schemas GenQL has been told to manage."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Connection, Engine, TextClause, text

from genql.domain.entities.schema_registration import SchemaRegistration
from genql.domain.errors import UnknownSchemaRegistrationError
from genql.domain.value_objects.schema_ref import SchemaRef

_COLUMNS = "datasource_name, schema_name, description, enabled, last_discovered_at"

_INSERT = text(f"""
    INSERT INTO genql.genql_schema ({_COLUMNS})
    VALUES (:datasource_name, :schema_name, :description, :enabled, :last_discovered_at)
    ON CONFLICT ON CONSTRAINT pk_genql_schema DO UPDATE
        SET description = EXCLUDED.description,
            enabled = EXCLUDED.enabled
""")

_SELECT_ONE = text(f"""
    SELECT {_COLUMNS} FROM genql.genql_schema
    WHERE datasource_name = :datasource_name AND schema_name = :schema_name
""")

_SELECT_FOR_DATASOURCE = text(f"""
    SELECT {_COLUMNS} FROM genql.genql_schema
    WHERE datasource_name = :datasource_name AND ((NOT :enabled_only) OR enabled)
    ORDER BY schema_name
""")

_SELECT_NAMES = text("""
    SELECT datasource_name || '.' || schema_name FROM genql.genql_schema ORDER BY 1
""")

_DELETE = text("""
    DELETE FROM genql.genql_schema
    WHERE datasource_name = :datasource_name AND schema_name = :schema_name
    RETURNING schema_name
""")

_MARK_DISCOVERED = text("""
    UPDATE genql.genql_schema SET last_discovered_at = now()
    WHERE datasource_name = :datasource_name AND schema_name = :schema_name
    RETURNING schema_name
""")


class PostgresSchemaRegistrationRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def add(self, registration: SchemaRegistration) -> None:
        with self._engine.begin() as conn:
            conn.execute(_INSERT, registration.model_dump(mode="json"))

    def get(self, ref: SchemaRef) -> SchemaRegistration:
        with self._engine.connect() as conn:
            row = conn.execute(_SELECT_ONE, ref.model_dump()).one_or_none()
            if row is None:
                raise UnknownSchemaRegistrationError(ref.qualified_name, self._names(conn))
        return SchemaRegistration.model_validate(row._mapping)  # noqa: SLF001

    def list_for_datasource(
        self, datasource_name: str, enabled_only: bool = False
    ) -> Sequence[SchemaRegistration]:
        with self._engine.connect() as conn:
            rows = conn.execute(
                _SELECT_FOR_DATASOURCE,
                {"datasource_name": datasource_name, "enabled_only": enabled_only},
            ).all()
        return [SchemaRegistration.model_validate(r._mapping) for r in rows]  # noqa: SLF001

    def remove(self, ref: SchemaRef) -> None:
        self._mutate(_DELETE, ref)

    def mark_discovered(self, ref: SchemaRef) -> None:
        self._mutate(_MARK_DISCOVERED, ref)

    def _mutate(self, statement: TextClause, ref: SchemaRef) -> None:
        with self._engine.begin() as conn:
            affected = conn.execute(statement, ref.model_dump()).scalar()
            if affected is None:
                raise UnknownSchemaRegistrationError(ref.qualified_name, self._names(conn))

    @staticmethod
    def _names(conn: Connection) -> list[str]:
        return [r[0] for r in conn.execute(_SELECT_NAMES).all()]
