"""The read side of Phase 3's mined join paths.

Lives beside PostgresJoinPathWriterRepository rather than in
repositories/query/ because it reads the table that package's sibling writes,
and splitting a table's reader from its writer across packages makes both
harder to keep in step.
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import Engine, text

from genql.domain.entities.join_path import JoinPath

_SELECT_JOIN_PATHS = text("""
    SELECT datasource_name, schema_name, source_object, target_object, path, weight, provenance
    FROM genql.genql_join_path
    WHERE datasource_name = :datasource_name
      AND (source_object = ANY(:object_names) OR target_object = ANY(:object_names))
    ORDER BY weight DESC, source_object, target_object
""")


class PostgresJoinPathReader:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def read_join_paths(
        self, datasource_name: str, object_names: Sequence[str]
    ) -> Sequence[JoinPath]:
        if not object_names:
            return []
        with self._engine.connect() as conn:
            rows = conn.execute(
                _SELECT_JOIN_PATHS,
                {"datasource_name": datasource_name, "object_names": list(object_names)},
            ).all()
        return [JoinPath.model_validate(r._mapping) for r in rows]  # noqa: SLF001
