"""Writes COMMENT ON TABLE / COMMENT ON COLUMN against the WAREHOUSE engine
— not the semantic store. `COMMENT ON` has no parameterized-identifier
form, so schema/object/column names are quoted through SQLAlchemy's own
IdentifierPreparer (which doubles embedded quote characters, the standard
SQL escaping rule) rather than interpolated raw; only the comment TEXT
itself is a bind parameter."""

from __future__ import annotations

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from genql.domain.errors import CompileError
from genql.domain.value_objects.schema_ref import SchemaRef
from genql.repositories.warehouse.registry import COMMENT_WRITERS


@COMMENT_WRITERS.register("postgres")
class PostgresCommentWriter:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def _quote(self, *parts: str) -> str:
        preparer = self._engine.dialect.identifier_preparer
        return ".".join(preparer.quote(p) for p in parts)

    def write_object_comment(self, ref: SchemaRef, object_name: str, comment: str) -> None:
        target = self._quote(ref.schema_name, object_name)
        try:
            with self._engine.begin() as conn:
                conn.execute(text(f"COMMENT ON TABLE {target} IS :comment"), {"comment": comment})
        except SQLAlchemyError as exc:
            raise CompileError(f"failed to write comment on {target}: {exc}") from exc

    def write_column_comment(
        self, ref: SchemaRef, object_name: str, column_name: str, comment: str
    ) -> None:
        target = self._quote(ref.schema_name, object_name, column_name)
        try:
            with self._engine.begin() as conn:
                conn.execute(text(f"COMMENT ON COLUMN {target} IS :comment"), {"comment": comment})
        except SQLAlchemyError as exc:
            raise CompileError(f"failed to write comment on {target}: {exc}") from exc
