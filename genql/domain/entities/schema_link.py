"""One retrieval hit bound to concrete SQL identifiers.

This is the whole output of schema linking: an object the retriever found,
plus the columns, mined join paths, and metrics that are actually usable
against it. Everything here is a name a generated statement may legally
mention, which is why the guardrails and the planner both read it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class SchemaLink(BaseModel):
    model_config = ConfigDict(frozen=True)

    object_qualified_name: str
    column_names: tuple[str, ...] = ()
    join_paths: tuple[str, ...] = ()
    metric_names: tuple[str, ...] = ()
    domain_id: int | None = None

    @property
    def schema_qualified_name(self) -> str:
        """`schema.object` — what appears in SQL, without the datasource prefix."""
        return self.object_qualified_name.split(".", 1)[1]
