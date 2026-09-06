"""Projects objects and FK edges into Neo4j, keyed on qualified_name.

MERGE makes both write methods idempotent: re-projecting an already-projected
schema changes nothing. Cross-schema foreign keys are out of scope here the
same way they are out of scope in `Constraint` itself — the entity carries no
`referenced_schema_name`, so a referenced object is always resolved within
the constraint's own schema.
"""

from __future__ import annotations

from collections.abc import Sequence

from neo4j import Driver

from genql.domain.entities.constraint import Constraint
from genql.domain.entities.database_object import DatabaseObject
from genql.domain.value_objects.constraint_type import ConstraintType

_ENSURE_CONSTRAINT = (
    "CREATE CONSTRAINT object_qualified_name IF NOT EXISTS "
    "FOR (o:Object) REQUIRE o.qualified_name IS UNIQUE"
)

_MERGE_OBJECTS = """
UNWIND $rows AS row
MERGE (o:Object {qualified_name: row.qualified_name})
SET o.datasource_name = row.datasource_name,
    o.schema_name = row.schema_name,
    o.object_name = row.object_name,
    o.object_type = row.object_type,
    o.row_estimate = row.row_estimate
"""

_MERGE_EDGES = """
UNWIND $rows AS row
MATCH (source:Object {qualified_name: row.source_qualified_name})
MATCH (target:Object {qualified_name: row.target_qualified_name})
MERGE (source)-[r:REFERENCES {constraint_name: row.constraint_name}]->(target)
SET r.column_names = row.column_names,
    r.referenced_column_names = row.referenced_column_names
"""


class Neo4jGraphWriterRepository:
    def __init__(self, driver: Driver) -> None:
        self._driver = driver
        self._constraint_ensured = False

    def write_objects(self, objects: Sequence[DatabaseObject]) -> int:
        if not objects:
            return 0
        self._ensure_constraint()
        rows = [
            {
                "qualified_name": o.qualified_name,
                "datasource_name": o.datasource_name,
                "schema_name": o.schema_name,
                "object_name": o.object_name,
                "object_type": o.object_type.value,
                "row_estimate": o.row_estimate,
            }
            for o in objects
        ]
        with self._driver.session() as session:
            session.run(_MERGE_OBJECTS, rows=rows)
        return len(rows)

    def write_edges(self, constraints: Sequence[Constraint]) -> int:
        rows = [
            {
                "source_qualified_name": f"{c.datasource_name}.{c.schema_name}.{c.object_name}",
                "target_qualified_name": (
                    f"{c.datasource_name}.{c.schema_name}.{c.referenced_object_name}"
                ),
                "constraint_name": c.constraint_name,
                "column_names": list(c.column_names),
                "referenced_column_names": list(c.referenced_column_names),
            }
            for c in constraints
            if c.constraint_type == ConstraintType.FOREIGN_KEY and c.referenced_object_name
        ]
        if not rows:
            return 0
        with self._driver.session() as session:
            session.run(_MERGE_EDGES, rows=rows)
        return len(rows)

    def _ensure_constraint(self) -> None:
        if self._constraint_ensured:
            return
        with self._driver.session() as session:
            session.run(_ENSURE_CONSTRAINT)
        self._constraint_ensured = True
